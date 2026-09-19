import re
from odoo import models, fields, api, _
from odoo.exceptions import UserError

METER_NUMBER_RE = re.compile(r'^NCWSC \d{6,8}$')


class MeterSwapWizard(models.TransientModel):
    _name = 'meter.swap.wizard'
    _description = 'Confirm Meter Swap'

    partner_id = fields.Many2one('res.partner', string='Customer', required=True, readonly=True)
    current_meter_number = fields.Char(string='Current Meter', readonly=True)
    active_history_id = fields.Many2one('meter.history', string='Active Meter Record', readonly=True)
    final_reading = fields.Float(
        string='Final Reading (m\u00b3)',
        help='Auto-fetched from the active meter history record. Locked if a reading '
             'is already on file; editable if it is still 0 and needs to be entered.'
    )
    has_existing_reading = fields.Boolean(
        default=False,
        help='True if a nonzero reading was already on file when this wizard opened. '
             'Used to lock the final_reading field so it cannot be accidentally overwritten.'
    )
    new_meter_number = fields.Char(
        string='New Meter Number',
        required=True,
        help='Format: NCWSC followed by a space and 6 to 8 digits (e.g. NCWSC 123456).'
    )

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        partner_id = self.env.context.get('default_partner_id')
        if partner_id:
            partner = self.env['res.partner'].browse(partner_id)
            active_history = self.env['meter.history'].search([
                ('partner_id', '=', partner.id),
                ('state', '=', 'active'),
            ], limit=1)
            res['partner_id'] = partner.id
            res['current_meter_number'] = partner.meter_number
            res['active_history_id'] = active_history.id
            res['final_reading'] = active_history.final_reading if active_history else 0.0
            res['has_existing_reading'] = bool(active_history and active_history.final_reading)
        return res

    def action_confirm_swap(self):
        self.ensure_one()
        if not self.new_meter_number:
            raise UserError(_("Enter the new meter number."))
        if not METER_NUMBER_RE.match(self.new_meter_number):
            raise UserError(_(
                "Meter number '%(value)s' is invalid. Expected format: 'NCWSC ' "
                "followed by 6 to 8 digits (e.g. NCWSC 123456).",
                value=self.new_meter_number,
            ))
        if self.new_meter_number == self.current_meter_number:
            raise UserError(_("The new meter number must be different from the current one."))
        if self.current_meter_number and self.final_reading <= 0.0:
            raise UserError(_(
                "Enter the final reading on the current meter (%(meter)s) before "
                "confirming the swap.",
                meter=self.current_meter_number,
            ))

        if self.active_history_id:
            self.active_history_id.write({'final_reading': self.final_reading})

        self.partner_id.write({'meter_number': self.new_meter_number})

        return {'type': 'ir.actions.act_window_close'}
