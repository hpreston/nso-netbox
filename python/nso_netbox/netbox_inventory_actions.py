import ncs
from ncs.dp import Action

# from _ncs import decrypt
import ncs.maapi as maapi
import _ncs.maapi as _maapi
from .netbox_utilities import verify_netbox, devicelist_netbox, vmlist_netbox
from ipaddress import ip_address
from datetime import datetime
import json
from _ncs.error import Error

# TODO: Move to utilities file
def get_users_groups(trans, uinfo):
    # Get the maapi socket
    s = trans.maapi.msock
    auth = _maapi.get_authorization_info(s, uinfo.usid)
    return list(auth.groups)


# Constancs and Values for use
PROTOCOL_PORTS = {
    "ssh": 22,
    "telent": 23,
    "http": 80,
    "https": 443,
}


class NetboxInventoryAction(Action):
    @Action.action
    def cb_action(self, uinfo, name, kp, action_input, action_output, trans):
        self.log.info("NetboxAction: ", name)
        service = ncs.maagic.get_node(trans, kp)
        root = ncs.maagic.get_root(trans)
        netbox_server = root.netbox_server[service.netbox_server]
        trans.maapi.install_crypto_keys()

        # Find groups user is a member of
        ugroups = get_users_groups(trans, uinfo)
        self.log.info("groups = ", ugroups)

        if name == "verify-inventory":
            self.verify_inventory(
                name, service, root, netbox_server, action_input, action_output
            )
        if name == "build-inventory":
            self.build_inventory(
                uinfo,
                ugroups,
                name,
                service,
                root,
                netbox_server,
                action_input,
                action_output,
            )
        if name == "connect-inventory":
            self.connect_inventory(
                uinfo,
                ugroups,
                name,
                service,
                root,
                netbox_server,
                action_input,
                action_output,
            )

    def build_inventory(
        self,
        uinfo,
        ugroups,
        name,
        service,
        root,
        netbox_server,
        action_input,
        action_output,
    ):
        """Add NetBox Devices for the Inventory to NSO as Devices."""

        build_status = True
        build_messages = []

        # See if the inventory service is configured to allow updating NSO Devices
        # TODO: Consider allowing a "dry-run" of building config even if false
        if not service.update_nso_devices:
            build_messages.append(
                f"NSO Inventory {service.name} has update-nso-devices set to {service.update_nso_devices}. No NSO <devices> will be created."
            )
            build_status = False

        # Check if NetBox Server reachable
        netbox_status = verify_netbox(netbox_server)
        if not netbox_status["status"]:
            build_messages.append(netbox_status["message"])
            build_status = False

        # Check if should proceed with building
        if not build_status:
            self.log.info("\n".join(build_messages))
            action_output.success = build_status
            action_output.output = "\n".join(build_messages)
            return

        # Create an output message that will be nice YAML friendly
        build_messages.append("# Adding Devices to NSO from NetBox inventory.")
        build_messages.append("devices: ")

        # Things good to build the inventory
        # Start a new Transaction Session
        with ncs.maapi.Maapi() as m:
            with ncs.maapi.Session(
                m, user=uinfo.username, context=name, groups=ugroups
            ):
                with m.start_write_trans() as t:

                    # Create new service object from a writeable transaction
                    writeable_service = ncs.maagic.get_node(t, service._path)
                    template = ncs.template.Template(writeable_service)

                    devices = []

                    # Only lookup devices if device_types provided
                    if service.device_type:
                        query = devicelist_netbox(service, netbox_server, log=self.log)
                        if query["status"]:
                            devices += query["result"]
                        else:
                            build_messages.append(
                                f"Unable to query to netbox server {netbox_server.url}"
                            )
                            build_messages.append(query["result"])
                            build_status = False
                            self.log.error("\n".join(build_messages))
                            action_output.success = build_status
                            action_output.output = "\n".join(build_messages)
                            return

                    # Lookup VMs if used in inventory
                    if service.vm_role:
                        vms_query = vmlist_netbox(service, netbox_server, log=self.log)

                        if vms_query["status"]:
                            # devices.append(vms_query["result"])
                            devices += vms_query["result"]
                        else:
                            action_output.output = vms_query["result"]
                            action_output.success = vms_query["status"]
                            return

                    for device in devices:
                        self.log.info(f"Processing device {device.name}")
                        # NetBox Status Field will affect results
                        #   Active          > Add / unlocked
                        #   Staged          > Add / unlocked
                        #   Offline         > Add / locked
                        #   Failed          > Add / locked
                        #   Decommissioning > Add / locked
                        #   Planned         > Add / southbound-locked
                        #   Inventory       > Remove
                        #
                        # If the service.admin_state is set, this overrides settings based on status
                        vars = ncs.template.Variables()
                        device_admin_state = None
                        if service.admin_state:
                            self.log.info(
                                f"Admin State configured to be {service.admin_state}, overriding status from NetBox"
                            )
                            device_admin_state = service.admin_state
                        else:
                            if device.status.value in ["active", "staged"]:
                                device_admin_state = "unlocked"
                            elif device.status.value in [
                                "offline",
                                "failed",
                                "decommissioning",
                            ]:
                                device_admin_state = "locked"
                            elif device.status.value in ["planned"]:
                                device_admin_state = "southbound-locked"
                            elif device.status.value in ["inventory"]:
                                self.log.info(
                                    f"NetBox status is {device.status}, removing device from NSO devices if found"
                                )
                                # TODO: Write removal code
                                continue

                            self.log.info(
                                f"NetBox status is {device.status}, setting Admin State to match"
                            )

                        # TODO: Create NSO Device Groups for Types/Models/Tenants that consolidate the groups from any NetBox Inventory Instance
                        # What NSO Device Groups to add device
                        nso_groups = [
                            f"NetBoxInventory {service.name}",
                            f"NetBoxInventory {service.name} {device.tenant.name}",
                        ]

                        # Device vs VM differences
                        if "devices" in device.url:
                            role = device.device_role
                            ned = service.device_type[device.device_type.model].ned
                            nso_groups.append(
                                f"NetBoxInventory {service.name} {device.device_type.model}"
                            )
                        elif "virtual-machines" in device.url:
                            role = device.role
                            ned = service.vm_role[device.role.name].ned

                        # Add role based group
                        nso_groups.append(
                            f"NetBoxInventory {service.name} {role.name}",
                        )

                        # Set Metadata on device for source of inventory info
                        source = {
                            "context": {
                                "web": device.url.replace("/api", ""),
                                "api": device.url,
                            },
                            "when": datetime.utcnow().isoformat(timespec="seconds"),
                            "source": service._path,
                        }

                        # Populate Variables for creating device
                        vars.add("DEVICE_NAME", device.name)
                        vars.add(
                            "DEVICE_ADDRESS",
                            ip_address(device.primary_ip.address.split("/")[0]),
                        )
                        vars.add("DEVICE_DESCRIPTION", role.name)
                        vars.add("AUTH_GROUP", service.auth_group)

                        # Determine if this NED is a "cli" or "generic"
                        device_package = root.packages.package[ned]
                        for component in device_package.component:
                            # Find the component that ties to the NED name
                            if component.name in ned:
                                # TODO: There is likely a better way to do this, but component.ned.cli is an ncs.maagic.Container, and can't figure out how to see if "empty" in Python
                                # Is it a CLI ned?
                                try:
                                    component.ned.cli.ned_id
                                    ned_type = "cli"
                                except Error:
                                    pass
                                # Is it a Generic NED
                                try:
                                    component.ned.generic.ned_id
                                    ned_type = "generic"
                                except Error:
                                    pass

                        # Port/Protocol Conversion Logic
                        if service.connection_protocol.string in PROTOCOL_PORTS.keys():
                            connection_port = PROTOCOL_PORTS[
                                service.connection_protocol.string
                            ]
                        else:
                            connection_port = ""

                        # Remaining Variables for template
                        vars.add("NED_ID", ned)
                        vars.add("NED_TYPE", ned_type)
                        vars.add("PROTOCOL", service.connection_protocol)
                        vars.add("PORT", connection_port)
                        vars.add("ADMIN_STATE", device_admin_state)
                        vars.add("SOURCE_CONTEXT", json.dumps(source["context"]))
                        vars.add("SOURCE_SOURCE", source["source"])
                        vars.add("SOURCE_WHEN", source["when"])
                        vars.add(
                            "BYPASS_CERT_VERIFY",
                            service.bypass_certificate_verification,
                        )

                        # Create output message for user
                        build_messages.append(f"- device: {device.name}")
                        build_messages.append(
                            f"  address: {ip_address(device.primary_ip.address.split('/')[0])}"
                        )
                        build_messages.append(f"  port: {connection_port}")
                        build_messages.append(f"  description: {role.name}")
                        build_messages.append(f"  auth-group: {service.auth_group}")

                        build_messages.append("  device-type: ")
                        build_messages.append(f"    {ned_type}:")
                        build_messages.append(f"      ned-id: {ned}")
                        build_messages.append(
                            f"      protocol: {service.connection_protocol}"
                        )

                        build_messages.append(f"    state: {device_admin_state}")
                        build_messages.append("    source:")
                        build_messages.append(
                            f"      context: {json.dumps(source['context'])}"
                        )
                        build_messages.append(f"      when: {source['when']}")
                        build_messages.append(f"      source: {source['source']}")

                        # Add devices to NSO Device-Groups
                        self.log.info(f"Device will be added to groups: {nso_groups}")
                        group_vars = ncs.template.Variables()
                        group_vars.add("DEVICE_NAME", device.name)
                        group_vars.add("DEVICE_GROUP_LOCATION", service._path)
                        build_messages.append("  device-groups: ")
                        for group in nso_groups:
                            group_vars.add("DEVICE_GROUP_NAME", group)
                            build_messages.append(f"  - {group}")

                            self.log.info(
                                f"Device {device.name} Group {group}: {group_vars}"
                            )

                            if action_input.commit:
                                self.log.info(
                                    "Applying template to add device to device-groups."
                                )
                                template.apply("add-device-group", group_vars)

                        self.log.info(f"Device {device.name}: {vars}")

                        # TODO: Look at using NSO "dry-run" feature
                        if action_input.commit:
                            self.log.info("Applying template to add device to NSO.")
                            template.apply("add-device", vars)

                            # Device/NED specific configuratons
                            if "cisco-fmc" in ned:
                                self.log.info(
                                    f"Device {device.name} uses ned {ned}. Applying Cisco FMC specific configurations."
                                )
                                template.apply("add-cisco-fmc", vars)
                            elif "vmware-vsphere" in ned:
                                self.log.info(
                                    f"Device {device.name} uses ned {ned}. Applying VMware specific configurations."
                                )
                                template.apply("add-vmware-vsphere-gen", vars)
                        else:
                            build_messages.append(
                                f"\n\n# Action input commit: {action_input.commit}. Devices will NOT be added to NSO."
                            )
                            build_status = False

                    t.apply()

        action_output.output = "\n".join(build_messages)
        action_output.success = build_status

    def connect_inventory(
        self,
        uinfo,
        ugroups,
        name,
        service,
        root,
        netbox_server,
        action_input,
        action_output,
    ):
        """Perform connection to devices in inventory. Include fetching ssh keys and optional sync-from."""

        connect_status = True
        connect_messages = []

        connect_messages.append(f"Connecting to devices from inventory {service.name}")

        # See if the inventory service is configured to allow updating NSO Devices
        if not service.update_nso_devices:
            connect_messages.append(
                f"NSO Inventory {service.name} has update-nso-devices set to {service.update_nso_devices}. No NSO <devices> will be created."
            )
            connect_status = False

        # Check if NetBox Server reachable
        netbox_status = verify_netbox(netbox_server)
        if not netbox_status["status"]:
            connect_messages.append(netbox_status["message"])
            connect_status = False

        devices = []

        # Only lookup devices if device_types provided
        if service.device_type:
            query = devicelist_netbox(service, netbox_server, log=self.log)
            if query["status"]:
                devices = query["result"]
            else:
                connect_messages.append(
                    f"Unable to query to netbox server {netbox_server.url}"
                )
                connect_messages.append(query["result"])
                connect_status = False
                self.log.error("\n".join(connect_messages))
                action_output.success = connect_status
                action_output.output = "\n".join(connect_messages)
                return

        # Lookup VMs if used in inventory
        if service.vm_role:
            vms_query = vmlist_netbox(service, netbox_server, log=self.log)

            if vms_query["status"]:
                devices += vms_query["result"]
            else:
                action_output.output = vms_query["result"]
                action_output.success = vms_query["status"]
                return

        for device in devices:
            self.log.info(f"Processing device {device.name}")

            # TODO: Verify device in NSO first

            connect_messages.append(f"Connecting to device {device.name}")

            if service.connection_protocol.string == "ssh":
                connect_messages.append("  - Fetching SSH Host-Keys")
                ssh_fetch = root.devices.device[device.name].ssh.fetch_host_keys()
                connect_messages.append(
                    f"    result: {ssh_fetch.result} {ssh_fetch.info}"
                )
                self.log.info(
                    f"{device.name} fetch ssh host key result: {ssh_fetch.result} {ssh_fetch.info}"
                )

            connect_messages.append("  - Testing Connecting to Device")
            connect = root.devices.device[device.name].connect()
            connect_messages.append(f"    result: {connect.result} {connect.info}")
            self.log.info(
                f"{device.name} connect result: {connect.result} {connect.info}"
            )

            if action_input.sync_from and connect.result:
                connect_messages.append("  - Performing sync-from")
                syncfrom = root.devices.device[device.name].sync_from()
                connect_messages.append(
                    f"    result: {syncfrom.result} {syncfrom.info}"
                )
                self.log.info(
                    f"{device.name} sync-from result: {syncfrom.result} {syncfrom.info}"
                )

        action_output.output = "\n".join(connect_messages)
        action_output.success = connect_status

    def verify_inventory(
        self, name, service, root, netbox_server, action_input, action_output
    ):
        """Verify that the NetBox Devices for the Inventory are present in NSO as Devices."""
        netbox_status = verify_netbox(netbox_server)
        if not netbox_status["status"]:
            action_output.success = netbox_status["status"]
            action_output.output = netbox_status["message"]
            return

        devices = []

        # Only lookup devices if device_types provided
        if service.device_type:
            query = devicelist_netbox(service, netbox_server, log=self.log)

            if query["status"]:
                devices += query["result"]
            else:
                action_output.output = query["result"]
                action_output.success = query["status"]
                return

        # Lookup VMs if used in inventory
        if service.vm_role:
            vms_query = vmlist_netbox(service, netbox_server, log=self.log)

            if vms_query["status"]:
                devices += vms_query["result"]
            else:
                action_output.output = vms_query["result"]
                action_output.success = vms_query["status"]
                return

        # Look for each NetBox device in the inventory
        verify_status = True
        verify_messages = []

        # if service.device_type:
        for device in devices:
            self.log.info(f"Testing device {device.name}")
            # Does the device exist
            try:
                nso_device = root.devices.device[device.name]
            except KeyError:
                # If NetBox lists device as "inventory" it shouldn't be found
                if device.status.value in ["inventory"]:
                    verify_messages.append(
                        f"Device {device.name} has a NetBox Status of {device.status.value}, it is not in NSO."
                    )
                else:
                    verify_messages.append(
                        f"Device {device.name} not found in NSO <devices>."
                    )
                    verify_status = False
                continue

            # If NetBox lists device as "inventory" it shouldn't be found
            if device.status.value in ["inventory"]:
                verify_messages.append(
                    f"Device {device.name} has a NetBox Status of {device.status.value}, it should NOT be in NSO but it is."
                )
                verify_status = False

            # Verify admin-state status of devices match NetBox status
            if (
                service.admin_state
                and nso_device.state.admin_state != service.admin_state
            ):
                verify_messages.append(
                    f"Device {device.name} has an admin_state of {nso_device.state.admin_state} which differs from service admin-state of {service.admin_state}"
                )
                verify_status = False
            else:
                if (
                    (
                        device.status.value in ["active", "staged"]
                        and nso_device.state.admin_state != "unlocked"
                    )
                    or (
                        device.status.value in ["offline", "failed", "decommissioning"]
                        and nso_device.state.admin_state != "locked"
                    )
                    or (
                        device.status.value in ["planned"]
                        and nso_device.state.admin_state != "southbound-locked"
                    )
                ):
                    verify_messages.append(
                        f"Device {device.name} has an admin_state of {nso_device.state.admin_state} which differs from NetBox status of {device.status.value}"
                    )
                    verify_status = False

            # Verify Address of device
            if ip_address(device.primary_ip.address.split("/")[0]) != ip_address(
                nso_device.address
            ):
                verify_messages.append(
                    f"Device {device.name} has a NetBox Primary IP of {device.primary_ip.address.split('/')[0]}, NSO device is configured for address {nso_device.address}"
                )
                verify_status = False

            # Device vs VM differences
            if "devices" in device.url:
                role = device.device_role
                ned = service.device_type[device.device_type.model].ned
            elif "virtual-machines" in device.url:
                role = device.role
                ned = service.vm_role[device.role.name].ned

            # Verify Description of Device
            if role.name != nso_device.description:
                verify_messages.append(
                    f"Device {device.name} has a NetBox Role of {role.name}, which doesn't match NSO description of {nso_device.description}"
                )
                verify_status = False

            # Determine if this NED is a "cli" or "generic"
            device_package = root.packages.package[ned]
            for component in device_package.component:
                # Find the component that ties to the NED name
                if component.name in ned:
                    # TODO: There is likely a better way to do this, but component.ned.cli is an ncs.maagic.Container, and can't figure out how to see if "empty" in Python
                    # Is it a CLI ned?
                    try:
                        component.ned.cli.ned_id
                        ned_type = "cli"
                    except Error:
                        pass
                    # Is it a Generic NED
                    try:
                        component.ned.generic.ned_id
                        ned_type = "generic"
                    except Error:
                        pass

            # Verify NED_ID
            if ned != nso_device.device_type[ned_type].ned_id.split(":")[1]:
                verify_messages.append(
                    f"Device {device.name} has a NetBox Device Type of {device.device_type.model} which should use NED {service.device_type[device.device_type.model].ned}, but is configured for NSO NED {nso_device.device_type.cli.ned_id.split(':')[1]}"
                )
                verify_status = False

            # Verify Protocol
            if ned_type == "cli" and str(service.connection_protocol) != str(
                nso_device.device_type.cli.protocol
            ):
                verify_messages.append(
                    f"Device {device.name} should use a connection protocol of {service.connection_protocol}, but is configured for {nso_device.device_type.cli.protocol}"
                )
                verify_status = False

            # Verify Port
            if nso_device.port != PROTOCOL_PORTS[service.connection_protocol.string]:
                verify_messages.append(
                    f"Device {device.name} should use a port of {PROTOCOL_PORTS[service.connection_protocol.string]}, but is configured for {nso_device.port}"
                )
                verify_status = False

        action_output.output = "\n".join(verify_messages)
        action_output.success = verify_status
