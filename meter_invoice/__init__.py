from . import models

def post_init_hook(env):
    """One-time backfill on module install/upgrade."""
    partners = env['res.partner'].search([
        ('account_number', '=', False),
        ('ref', '!=', False),
    ])
    for partner in partners:
        partner.account_number = partner.ref

    histories = env['meter.history'].search([('account_number', '=', False)])
    for history in histories:
        if history.partner_id.account_number:
            history.account_number = history.partner_id.account_number
