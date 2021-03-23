# nso-netbox

This will be an NSO package for interacting with NetBox as a source of truth. Example use cases include: 

* Generating a device inventory from NetBox devices 
* IP Address/Prefix Allocation
* Gathering data for verification checks 

## Using the nso-netbox package
This short walkthrough will show how the nso-netbox package can be used to integrate NetBox with Cisco NSO. This walkthrough is intended to highlight the use of the package, **NOT** how the package was built. 

## Add a NetBox Server to NSO 
1. The first step for any interaction involves adding a NetBox Server instance to to NSO. To add the server, you'll need the following information. 
    * The FQDN or IP Address for the NetBox server 
    * An API token for a user. Read-Only permissions on the token should be sufficient 
    * The protocol (http / https) and port (80 / 443) that NetBox is listening on. 
1. With that information, you can add this block of configuration to NSO. 

    ```
    netbox-server example-vm-netbox-01.example.net
        fqdn      example-netbox-01.example.net
        port      80
        protocol  http
        api-token uana9a8nakduandkadda68c6885383b16feefe3
    ```

    > Note: If you are using IP address, you'd configure the `address 172.23.80.1` instead of `fqdn`. 
    > Note: The service defaults to `protocol https` and `port 443`

1. Once committed to NSO, an additional value for the `netbox-server` is constructed to represent the URL for the server. 

    ```
    localadmin@ncs# show netbox-server example-vm-netbox-01.example.net url 

    url http://example-netbox-01.example.net:80
    ```

1. It is always a good idea to verify that NSO can communicate with NetBox after adding a new server. You can do so with this action. 

    ```
    netbox-server example-vm-netbox-01.example.net verify-status 

    # Sample Output
    output NetBox Version: 2.10.4, Python Version: 3.8.7, Plugins: {}, Workers Running: 1
    success true
    ```

    > Note: A communciation verification to the server is run by most other actions before attempting to take any action. 

## Verifying the NSO Devices match NetBox 
As the "Source of Truth", the devices listed in NetBox (including thier address, types, and status) should drive what NSO has in it's own inventory. We can do this check and verification by adding a `netbox-inventory` object to NSO. 

1. A `netbox-inventory` configuration is a query or filter that NSO will use to lookup a subset of devices from NetBox to work with. This filter can include the following characteristics. 
    * `site` - The NetBox Site the devices are a member of 
    * `tenant` - The NetBox Tenant that the device is associated to 
    * `device-role` - The NetBox Device Role assigned to the device 
    * `device-type` - The NetBox Device Type of the device
    * `vm-role` - The NetBox Device Role for Virtual Machines to be added to inventory. 
        * *See below for more details*

    > Note: Each characteristic can be added more than once. A device would simply need to match one of the possible values listed to be selected.
1. Every `netbox-inventory` requires at least one `device-type` or `vm-role` be configured. Furthermore, for each of these configured, you must specify the NSO NED that corresponds to this device. 
1. In addition to the filters used to query NetBox, you also need to specify the following values for a `netbox-inventory`. 
    * `auth-group` - The NSO `devices auth-group` that should be used for the devices that match the query 
    * `netbox-server` - The `netbox-server` instance you are querying with this inventory
1. With this information available, you can create the following configuration. 

    ```
    netbox-inventory router-verify
        auth-group         localadmin
        netbox-server      example-vm-netbox-01.example.net
        site               [ MYDC ]
        tenant             [ example-admin ]
        device-type "CSR 1000v-physical"
        ned cisco-ios-cli-6.69
    ```

1. After you've committed this configuration, you can now check to see if the NSO `<devices>` that match this query are configured correctly with this NSO action. 

    ```
    netbox-inventory router-verify verify-inventory

    # Example Output when all is correct
    output 
    success true
    ```

1. In the output above, everything is correct in NSO. But suppose something didn't match. You'd get an output such as this. 

    ```
    netbox-inventory router-verify verify-inventory

    # Output with errors
    output Device example-rtr-dmz-01 not found in NSO <devices>.
    Device example-rtr-edge-02 has a NetBox Primary IP of 172.31.128.14, NSO device is configured for address 1.1.1.1
    Device example-rtr-edge-02 has a NetBox Role of Virtual/Physical Router, which doesn't match NSO description of None
    success false
    ```

    > Note: The `success false` indicates at least one difference was found. And the `output` highlights the differences. 

1. You could manually fix these errors, or move to the next section to see how this can be done automatically. 

## Building NSO <devices> from NetBox 
Verifying that the data in NSO matches the Source of Truth is a great first step, but wouldn't it be great to just enforce the configuration from NetBox to NSO?  Of course it would. 

1. Start by updating the `netbox-inventory` configuration to support updating NSO by setting the `update-nso-devices` value to `true`. The default value is `false` to prevent unintended configuration updates. 

    ```
    netbox-inventory router-verify
        update-nso-devices true
    ```

1. Now you can take advantage of the `build-inventory` action.  

    ```yaml
    netbox-inventory router-verify build-inventory 

    # Sample Output
    output # Adding Devices to NSO from NetBox inventory.
    devices: 
    - device: example-rtr-dmz-01
    address: 172.31.128.21
    description: Virtual/Physical Router
    auth-group: localadmin
    device-type: 
        cli:
        ned-id: cisco-ios-cli-6.69
        protocol: ssh
        state: unlocked
        source:
        context: {"web": "http://example-netbox-01.example.net/dcim/devices/205/", "api": "http://example-netbox-01.example.net/api/dcim/devices/205/"}
        when: 2021-03-18T13:55:02
        source: /nso-netbox:netbox-inventory{router-verify}
    device-groups: 
    - NetBoxInventory router-verify:
    - NetBoxInventory router-verify CSR 1000v-physical:
    - NetBoxInventory router-verify Virtual/Physical Router:
    - NetBoxInventory router-verify example-admin:


    # Action input commit: False. Devices will NOT be added to NSO.
    - device: example-rtr-dmz-02
    address: 172.31.128.22
    description: Virtual/Physical Router
    auth-group: localadmin
    device-type: 
        cli:
        ned-id: cisco-ios-cli-6.69
        protocol: ssh
        state: unlocked
        source:
        context: {"web": "http://example-netbox-01.example.net/dcim/devices/206/", "api": "http://example-netbox-01.example.net/api/dcim/devices/206/"}
        when: 2021-03-18T13:55:02
        source: /nso-netbox:netbox-inventory{router-verify}
    device-groups: 
    - NetBoxInventory router-verify:
    - NetBoxInventory router-verify CSR 1000v-physical:
    - NetBoxInventory router-verify Virtual/Physical Router:
    - NetBoxInventory router-verify example-admin:


    # Action input commit: False. Devices will NOT be added to NSO.
    - device: example-rtr-edge-01
    address: 172.31.128.13
    description: Virtual/Physical Router
    auth-group: localadmin
    device-type: 
        cli:
        ned-id: cisco-ios-cli-6.69
        protocol: ssh
        state: unlocked
        source:
        context: {"web": "http://example-netbox-01.example.net/dcim/devices/201/", "api": "http://example-netbox-01.example.net/api/dcim/devices/201/"}
        when: 2021-03-18T13:55:02
        source: /nso-netbox:netbox-inventory{router-verify}
    device-groups: 
    - NetBoxInventory router-verify:
    - NetBoxInventory router-verify CSR 1000v-physical:
    - NetBoxInventory router-verify Virtual/Physical Router:
    - NetBoxInventory router-verify example-admin:


    # Action input commit: False. Devices will NOT be added to NSO.
    - device: example-rtr-edge-02
    address: 172.31.128.14
    description: Virtual/Physical Router
    auth-group: localadmin
    device-type: 
        cli:
        ned-id: cisco-ios-cli-6.69
        protocol: ssh
        state: unlocked
        source:
        context: {"web": "http://example-netbox-01.example.net/dcim/devices/202/", "api": "http://example-netbox-01.example.net/api/dcim/devices/202/"}
        when: 2021-03-18T13:55:02
        source: /nso-netbox:netbox-inventory{router-verify}
    device-groups: 
    - NetBoxInventory router-verify:
    - NetBoxInventory router-verify CSR 1000v-physical:
    - NetBoxInventory router-verify Virtual/Physical Router:
    - NetBoxInventory router-verify example-admin:


    # Action input commit: False. Devices will NOT be added to NSO.
    success false
    ```

1. In the output above, notice the final line of output.  There is a flag to the `build-inventory` action for `commit`.  If you don't explicitly set this to `commit true`, it is kinda like a `dry-run`.  You'll see the configuration to be applied, but it won't actually apply the configuration. This is a second protection from unintended configuration changes to NSO.  
1. In addition to adding the devices that match the inventory, several `device-groups` are created for the inventory. There will be groups for: 
    * The entire `netbox-inventory` instance 
    * The `device-types` of each device 
    * The `device-roles` for each device 
    * THe `tenants` for each device 

    > Note: even if the attributes are NOT used as filters in the inventory, the groups are still created

1. To actually apply the configuration, run the `build-inventory commit true` command. 

    ```yaml
    netbox-inventory router-verify build-inventory commit true 

    # Sample output - some content removed for brevity 
    output # Adding Devices to NSO from NetBox inventory.
    devices: 
    - device: example-rtr-dmz-01
    address: 172.31.128.21
    description: Virtual/Physical Router
    auth-group: localadmin
    device-type: 
        cli:
        ned-id: cisco-ios-cli-6.69
        protocol: ssh
        state: unlocked
        source:
        context: {"web": "http://example-netbox-01.example.net/dcim/devices/205/", "api": "http://example-netbox-01.example.net/api/dcim/devices/205/"}
        when: 2021-03-18T14:00:45
        source: /nso-netbox:netbox-inventory{router-verify}
    device-groups: 
    - NetBoxInventory router-verify:
    - NetBoxInventory router-verify CSR 1000v-physical:
    - NetBoxInventory router-verify Virtual/Physical Router:
    - NetBoxInventory router-verify example-admin:
    .
    .
    .
    success true
    localadmin@ncs# 
    System message at 2021-03-18 14:00:45...
    Commit performed by localadmin via tcp using build-inventory.
    ```

1. This time you see `success true` at the end of the output. Also there is the message from NSO that a commit was performed. 
1. To verify the inventory was applied correctly, you can run the `verify-inventory` once again. 

## Adding SSH Keys, Verifying Connection to Devices, and initial Sync-From 
The first time a new device is added to NSO there are a few steps that need to be taken to complete the connection. These include: 

* Fetching SSH Host-Keys (if SSH is used instead of Telnet)
* Attempting to `connect` to the device to make sure the credentials are working 
* Performing a `sync-from` to update the NSO CDB with the initial configuration for the device. 

These steps could be done manually, but there is an action on the `netbox-inventory` that will make this easier. 

1. First, let's run the `connect-inventory` action. 
    > Note: this action can take a long time if you have many devices that match the filter 

    ```
    netbox-inventory router-verify connect-inventory 

    # Sample Output
    output Connecting to devices from inventory router-verify
    Connecting to device example-rtr-dmz-01
    - Fetching SSH Host-Keys
        result: updated None
    - Testing Connecting to Device
        result: True (localadmin) Connected to example-rtr-dmz-01 - 172.31.128.21:22
    Connecting to device example-rtr-dmz-02
    - Fetching SSH Host-Keys
        result: unchanged None
    - Testing Connecting to Device
        result: True (localadmin) Connected to example-rtr-dmz-02 - 172.31.128.22:22
    Connecting to device example-rtr-edge-01
    - Fetching SSH Host-Keys
        result: unchanged None
    - Testing Connecting to Device
        result: True (localadmin) Connected to example-rtr-edge-01 - 172.31.128.13:22
    Connecting to device example-rtr-edge-02
    - Fetching SSH Host-Keys
        result: unchanged None
    - Testing Connecting to Device
        result: True (localadmin) Connected to example-rtr-edge-02 - 172.31.128.14:22
    success true
    ```

    * You'll get status messages letting you know the results of fetching keys and connecting. If an error is found in this step you should work to fix the configuration for the inventory. The most likely candidates for problems are incorrect `primary-ips` for devices in NetBox or devices where the credentials in the configured `auth-group` aren't correct. 

1. But there is nothing about a `sync-from` in the output above.  By default `connect-inventory` will only grab SSH keys and try to connect. To `sync-from` you need to set this true. 
    > Note: this action can take a long time if you have many devices that match the filter 

    ```
    netbox-inventory router-verify connect-inventory sync-from true 

    # Sample output - edited for brevity 
    output Connecting to devices from inventory router-verify
    Connecting to device example-rtr-dmz-01
    - Fetching SSH Host-Keys
        result: unchanged None
    - Testing Connecting to Device
        result: True (localadmin) Connected to example-rtr-dmz-01 - 172.31.128.21:22
    - Performing sync-from
        result: True None
    .
    .
    .
    success true
    ```

    * Now you see the `Performing sync-from` in the output

## Using nso-netbox after initial inventory setup 
While this package is clearly useful to get the initial devices setup correctly in NSO to match NetBox, the ability to run the `verify-inventory` action at anytime is key to making sure NSO stays aligned to the Source of Truth. Some ideas on how to do this would be: 

* Scheduling regular runs of `verify-inventory` to occur using the RESTCONF or NETCONF API for NSO
* If the action `fails`, an alert should be generated
* Optionally, if your team is very disciplined with Source of Truth based automation, you could automatically run the `build-inventory` and `connect-inventory` actions when `verify-inventory` fails

## NetBox Virtual Machine and NSO 
While the majority of devices within NSO will be represented by NetBox devices, there are some that maybe in NetBox as Virtual Machines. For example, Cisco Firepower Management Center and vCenter Applicances can be added to Cisco NSO but they are more likely to be represented in NetBox as VMs than devices.  

Within NetBox, there is no concept of `device-types` for VMs. But a `device-role` can be associated to Virtual Machines.  To support VMs within `netbox-inventory`, you can add a `vm-role`.  Like `device-type`, `vm-role` takes a required `ned` to link the NetBox VM Role to a NED.  

Here is an example for a FirewPower Management Center

```
netbox-inventory firepower-management-center
 auth-group          fmc
 connection-protocol https
 update-nso-devices  true
 netbox-server       example-vm-netbox-01.example.net
 site                [ MYDC ]
 tenant              [ example-admin ]
 vm-role "Firepower Management Center (FMC)"
  ned cisco-fmc-gen-1.5
  ```

## NED Specific Settings 
In addition to device configurations that are fairly common across all devices, NSO supports specific settings per NED.  For these NED/Device specific configurations, you can either configure them manually after running the `build-inventory` process, or update the service/package to configure them for you.  

There are some common ned-settings included with the package already. These settings are implemented with two parts of the package: 

1. An XML template specific to the device. The templates are named `add-NED-NAME.xml`. 

    ```
    ls -l packages/nso-netbox/templates/

    -rw-rw-r-- 1 hapresto hapresto  533 Mar 22 17:09 add-cisco-fmc.xml
    -rw-rw-r-- 1 hapresto hapresto  640 Mar 22 17:06 add-vmware-vsphere-gen.xml
    ```

1. Logic in the `build-inventory` action code in the `netbox_inventory_actions.py` file that looks at the NED for a device and applies the NED specific configuration if needed. 

    ```
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
    ```

> ***When loading a package/service, NSO verifies that any NED referenced in the templates is also loaded. If there are templates that use NEDs not loaded, NSO will generate an error.  In this case the simplest thing to do is move the extra templates out of the `templates` directory and reloading the package.***  

In it's current state, `nso-netbox` has the following net-settings implemented. 

### cisco-fmc 

```
devices device dev01-z0-vm-fmc-01
 ned-settings cisco-fmc cisco-fmc-connection ssl accept-any true
```

### vmware-vsphere

```
devices device dev01-z0-vm-vcenter-02
 read-timeout  60
 write-timeout 60
 ned-settings vmware-vsphere device-flavor portgroup-cfg
 ned-settings vmware-vsphere connection ssl-version TLSv1.2
```