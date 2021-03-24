"""Set of reusable functions for NetBox

"""

import pynetbox
from requests import exceptions
from _ncs import decrypt
from pynetbox.core.query import RequestError


def verify_netbox(netbox_server):
    """Verify a NetBox Server is reachable"""
    nb = pynetbox.api(netbox_server.url, token=decrypt(netbox_server.api_token))
    try:
        status = nb.status()
    except RequestError as e: 
        # Older versions of NetBox don't have the status api, try to retrieve devices
        devices = nb.dcim.devices.all()
        return {
            "status": True, 
            "message": f"Successfully connected to NetBox to query devices."
        }
    except exceptions.ConnectionError:
        return {
            "status": False,
            "message": f"Error connecting to NetBox Server at url {netbox_server.url}.",
        }

    status_message = f"NetBox Version: {status['netbox-version']}, Python Version: {status['python-version']}, Plugins: {status['plugins']}, Workers Running: {status['rq-workers-running']}"
    return {"status": True, "message": status_message}


def query_netbox(object, log=False, **query):
    """Send a filter query to NetBox for an object"""
    results = object.filter(**query)
    if log:
        log.info(f"  Results: {results}")

    return results


def devicelist_netbox(netbox_inventory, netbox_server, log=False):
    """Retrieve matching devices from NetBox for an inventory"""

    try:
        nb = pynetbox.api(netbox_server.url, token=decrypt(netbox_server.api_token))

        # Build the device query from the provided attributes to the inventory instance
        device_query = {}
        if netbox_inventory.site:
            if log:
                log.info("Looking up NetBox Sites to Filter.")
            sites = query_netbox(
                nb.dcim.sites, log, name=[site for site in netbox_inventory.site]
            )
            device_query["site_id"] = [site.id for site in sites]

        if netbox_inventory.tenant:
            if log:
                log.info("Looking up NetBox Tenants to Filter.")
            tenants = query_netbox(
                object=nb.tenancy.tenants,
                log=log,
                name=[tenant for tenant in netbox_inventory.tenant],
            )
            device_query["tenant_id"] = [tenant.id for tenant in tenants]

        if netbox_inventory.device_type:
            if log:
                log.info("Looking up NetBox Device-Types to Filter.")
            device_types = query_netbox(
                object=nb.dcim.device_types,
                log=log,
                model=[
                    device_type.model for device_type in netbox_inventory.device_type
                ],
            )
            device_query["device_type_id"] = [
                device_type.id for device_type in device_types
            ]

        if netbox_inventory.device_role:
            if log:
                log.info("Looking up NetBox Device-Roles to Filter.")
            device_roles = query_netbox(
                object=nb.dcim.device_roles,
                log=log,
                name=[device_role for device_role in netbox_inventory.device_role],
            )
            device_query["role_id"] = [device_role.id for device_role in device_roles]

        if log:
            log.info(f"Looking up NetBox Devices for Filter: {device_query}")
        devices = query_netbox(object=nb.dcim.devices, log=log, **device_query)

        return {"status": True, "result": devices}
    except Exception as e:
        if log:
            log.error(f"Lookup failed: {e}")
        return {"status": False, "result": e}


def vmlist_netbox(netbox_inventory, netbox_server, log=False):
    """Retrieve matching Virtual Machines from NetBox for an inventory"""

    try:
        nb = pynetbox.api(netbox_server.url, token=decrypt(netbox_server.api_token))

        # Build the VM query from the provided attributes to the inventory instance
        vm_query = {}
        if netbox_inventory.site:
            if log:
                log.info("Looking up NetBox Sites to Filter.")
            sites = query_netbox(
                nb.dcim.sites, log, name=[site for site in netbox_inventory.site]
            )
            vm_query["site_id"] = [site.id for site in sites]

        if netbox_inventory.tenant:
            if log:
                log.info("Looking up NetBox Tenants to Filter.")
            tenants = query_netbox(
                object=nb.tenancy.tenants,
                log=log,
                name=[tenant for tenant in netbox_inventory.tenant],
            )
            vm_query["tenant_id"] = [tenant.id for tenant in tenants]

        if netbox_inventory.vm_role:
            if log:
                log.info("Looking up NetBox Virtual Machine Roles to Filter.")
            vm_roles = query_netbox(
                object=nb.dcim.device_roles,
                log=log,
                name=[vm_role.role for vm_role in netbox_inventory.vm_role],
                vm_role=True,
            )
            vm_query["role_id"] = [vm_role.id for vm_role in vm_roles]

        if log:
            log.info(f"Looking up NetBox vms for Filter: {vm_query}")
        vms = query_netbox(object=nb.virtualization.virtual_machines, log=log, **vm_query)

        return {"status": True, "result": vms}
    except Exception as e:
        if log:
            log.error(f"Lookup failed: {e}")
        return {"status": False, "result": e}
