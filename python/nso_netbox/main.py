# -*- mode: python; python-indent: 4 -*-
import ncs
from ncs.application import Service
from .actions import NetboxServerAction
from .netbox_inventory import NetboxInventoryServiceCallbacks
from .netbox_inventory_actions import NetboxInventoryAction


# ------------------------
# SERVICE CALLBACK EXAMPLE
# ------------------------
class NetboxServerServiceCallbacks(Service):

    # The create() callback is invoked inside NCS FASTMAP and
    # must always exist.
    @Service.create
    def cb_create(self, tctx, root, service, proplist):
        self.log.info("Service create(service=", service._path, ")")

        # Use the provided connection details for the server to craft the URL to connect to
        if service.fqdn:
            netbox_url = f"{service.protocol}://{service.fqdn}:{service.port}"
        else:
            netbox_url = f"{service.protocol}://{service.address}:{service.port}"
        self.log.info(f"NetBox url: {netbox_url}")
        # TODO: After restarting NSO this value seems to go away until re-commit
        service.url = netbox_url

        # vars = ncs.template.Variables()
        # vars.add('DUMMY', '127.0.0.1')
        # template = ncs.template.Template(service)
        # template.apply('nso-netbox-template', vars)

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


# ---------------------------------------------
# COMPONENT THREAD THAT WILL BE STARTED BY NCS.
# ---------------------------------------------
class Main(ncs.application.Application):
    def setup(self):
        # The application class sets up logging for us. It is accessible
        # through 'self.log' and is a ncs.log.Log instance.
        self.log.info("Main RUNNING")

        # Service callbacks require a registration for a 'service point',
        # as specified in the corresponding data model.
        #
        self.register_service(
            "nso-netbox-server-servicepoint", NetboxServerServiceCallbacks
        )
        self.register_service(
            "nso-netbox-inventory-servicepoint", NetboxInventoryServiceCallbacks
        )
        self.register_action("netbox-verify-status", NetboxServerAction)
        self.register_action("netbox-inventory-build", NetboxInventoryAction)
        self.register_action("netbox-inventory-connect", NetboxInventoryAction)
        self.register_action("netbox-inventory-remove", NetboxInventoryAction)
        self.register_action("netbox-inventory-verify", NetboxInventoryAction)

        # If we registered any callback(s) above, the Application class
        # took care of creating a daemon (related to the service/action point).

        # When this setup method is finished, all registrations are
        # considered done and the application is 'started'.

    def teardown(self):
        # When the application is finished (which would happen if NCS went
        # down, packages were reloaded or some error occurred) this teardown
        # method will be called.

        self.log.info("Main FINISHED")
