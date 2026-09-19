import re
from odoo import models, fields, api, _
from odoo.exceptions import ValidationError

METER_NUMBER_RE = re.compile(r'^NCWSC \d{6,8}$')


class MeterHistory(models.Model):
    _name = 'meter.history'
    _description = 'Customer Meter Assignment and History'
    _order = 'start_date desc, id desc'

    partner_id = fields.Many2one(
        'res.partner',
        string='Customer',
        required=True,
        ondelete='cascade'
    )

    account_number = fields.Char(
        string='Account Number',
        help='Snapshot of the customer\'s account number at the time this '
             'meter record was created. Frozen historically - does not '
             'change if the customer\'s account number is edited later.'
    )

    meter_number = fields.Char(
        string='Meter Serial No.',
        required=True,
        help='Format: NCWSC followed by a space and 6 to 8 digits (e.g., NCWSC 123456).'
    )

    start_date = fields.Date(
        string='Installation Date',
        default=fields.Date.context_today,
        required=True
    )

    end_date = fields.Date(
        string='Removal / Swap Date'
    )

    final_reading = fields.Float(
        string='Final Reading (m3)',
        default=0.0,
        help='Enter the reading on this meter right before it is swapped out. '
             'Required (must be greater than 0) before the meter_number change '
             'on the customer form will be allowed to process.'
    )

    state = fields.Selection([
        ('active', 'Active'),
        ('replaced', 'Replaced')
    ], string='Status', default='active', required=True)

    notes = fields.Text(string='Notes / Reason for Swap')

    @api.constrains('meter_number')
    def _check_meter_number_format(self):
        for record in self:
            if record.meter_number and not METER_NUMBER_RE.match(record.meter_number):
                raise ValidationError(_(
                    "Meter number '%(value)s' is invalid. Expected format: 'NCWSC ' "
                    "followed by 6, 7, or 8 digits (e.g., NCWSC 123456).",
                    value=record.meter_number,
                ))

    @api.constrains('partner_id', 'state')
    def _check_single_active_meter(self):
        for record in self:
            if record.state != 'active':
                continue
            duplicate = self.search_count([
                ('partner_id', '=', record.partner_id.id),
                ('state', '=', 'active'),
                ('id', '!=', record.id),
            ])
            if duplicate:
                raise ValidationError(_(
                    "%(partner)s already has an active meter (%(meter)s). "
                    "Replace the existing meter before adding a new one.",
                    partner=record.partner_id.display_name,
                    meter=record.meter_number,
                ))
