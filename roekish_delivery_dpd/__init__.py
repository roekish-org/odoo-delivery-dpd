from . import models
from . import wizards


def post_init_hook(env):
    """Seed the administrator into the DPD Administrator group.

    In Odoo 19 res.users groups are role-managed and cannot be set reliably
    from a data record, so we grant the group here so the module is usable
    right after install.
    """
    admin = env.ref("base.user_admin", raise_if_not_found=False)
    group = env.ref("roekish_delivery_dpd.group_dpd_manager", raise_if_not_found=False)
    if admin and group:
        admin.sudo().write({"group_ids": [(4, group.id)]})
