import ncs
from ncs.dp import Action

# from _ncs import decrypt
from .netbox_utilities import verify_netbox


class NetboxServerAction(Action):
    @Action.action
    def cb_action(self, uinfo, name, kp, action_input, action_output, trans):
        self.log.info("NetboxAction: ", name)
        service = ncs.maagic.get_node(trans, kp)
        root = ncs.maagic.get_root(trans)
        # trans.maapi.install_crypto_keys()

        if name == "verify-status":
            self.verify_status(service, root, action_output)

    def verify_status(self, service, root, action_output):
        """Perform a status check that the NetBox server is reachable."""
        netbox_status = verify_netbox(service)
        action_output.success = netbox_status["status"]
        action_output.output = netbox_status["message"]
        self.log.info(
            f'Verification Results: {netbox_status["status"]} {netbox_status["message"]}'
        )
