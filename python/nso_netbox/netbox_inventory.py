# -*- mode: python; python-indent: 4 -*-
import ncs
from ncs.application import Service
from .netbox_utilities import verify_netbox, devicelist_netbox
from ipaddress import ip_address


# ------------------------
# SERVICE CALLBACK EXAMPLE
# ------------------------
class NetboxInventoryServiceCallbacks(Service):

    # The create() callback is invoked inside NCS FASTMAP and
    # must always exist.
    @Service.create
    def cb_create(self, tctx, root, service, proplist):
        self.log.info("Service create(service=", service._path, ")")

        # TODO: How can I fire off and verify an action before commit?  pre_modification?

        if not service.update_nso_devices:
            self.log.info(
                f"NSO Inventory {service.name} has update-nso-devices set to {service.update_nso_devices}. No NSO <devices> will be created."
            )
            return

    # The pre_modification() and post_modification() callbacks are optional,
    # and are invoked outside FASTMAP. pre_modification() is invoked before
    # create, update, or delete of the service, as indicated by the enum
    # ncs_service_operation op parameter. Conversely
    # post_modification() is invoked after create, update, or delete
    # of the service. These functions can be useful e.g. for
    # allocations that should be stored and existing also when the
    # service instance is removed.

    # @Service.pre_lock_create
    # def cb_pre_lock_create(self, tctx, root, service, proplist):
    #     self.log.info('Service plcreate(service=', service._path, ')')

    # @Service.pre_modification
    # def cb_pre_modification(self, tctx, op, kp, root, proplist):
    #     self.log.info('Service premod(service=', kp, ')')

    # @Service.post_modification
    # def cb_post_modification(self, tctx, op, kp, root, proplist):
    #     self.log.info('Service postmod(service=', kp, ')')
