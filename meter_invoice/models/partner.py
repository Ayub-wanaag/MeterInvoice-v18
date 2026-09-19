import re
from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError

ACCOUNT_NUMBER_RE = re.compile(r'^\d{7}$')
METER_NUMBER_RE = re.compile(r'^NCWSC \d{6,8}$')


class ResPartner(models.Model):
    _inherit = 'res.partner'

    account_number = fields.Char(
        string='Account Number',
        copy=False,
        help='Nairobi Water account number - must be exactly 7 digits, e.g. 1048506.'
    )

    meter_number = fields.Char(
        string='Meter Number',
        help='Water meter serial number. Format: NCWSC followed by a space and 6 to 8 digits '
             '(e.g. NCWSC 123456).'
    )

    customer_category_id = fields.Many2one(
        'customer.category',
        string='Customer Category',
        help='Determines which billing tier rates apply'
    )

    is_bh = fields.Boolean(
        related='customer_category_id.is_bh',
        string='Is Borehole Category'
    )

    category_water_tier_ids = fields.One2many(
        related='customer_category_id.water_tier_ids',
        string='Water Tiers',
        readonly=True
    )

    category_sewerage_tier_ids = fields.One2many(
        related='customer_category_id.sewerage_tier_ids',
        string='Sewerage Tiers',
        readonly=True
    )

    @api.constrains('account_number')
    def _check_account_number_unique(self):
        # Replaces the old `_sql_constraints` unique index: Odoo 19 removed
        # the classic `_sql_constraints` list attribute in favour of
        # `models.Constraint`, which in turn doesn't exist on Odoo 18 (or 17).
        # A plain Python constraint works unchanged on 17, 18 and 19.
        for partner in self:
            if not partner.account_number:
                continue
            duplicate = self.with_context(active_test=False).search_count([
                ('account_number', '=', partner.account_number),
                ('id', '!=', partner.id),
            ])
            if duplicate:
                raise ValidationError(_(
                    "This account number is already assigned to another customer."
                ))

    @api.constrains('account_number')
    def _check_account_number_format(self):
        for partner in self:
            if partner.account_number and not ACCOUNT_NUMBER_RE.match(partner.account_number):
                raise ValidationError(_(
                    "Account number '%(value)s' is invalid. Nairobi Water account "
                    "numbers must be exactly 7 digits (e.g. 1048506).",
                    value=partner.account_number,
                ))

    @api.constrains('meter_number')
    def _check_meter_number_format(self):
        for partner in self:
            if partner.meter_number and not METER_NUMBER_RE.match(partner.meter_number):
                raise ValidationError(_(
                    "Meter number '%(value)s' is invalid. Expected format: 'NCWSC ' "
                    "followed by 6, 7, or 8 digits (e.g. NCWSC 123456).",
                    value=partner.meter_number,
                ))

    @api.model_create_multi
    def create(self, vals_list):
        partners = super().create(vals_list)
        for partner in partners:
            if partner.meter_number:
                self.env['meter.history'].create({
                    'partner_id': partner.id,
                    'meter_number': partner.meter_number,
                    'account_number': partner.account_number,
                    'state': 'active',
                    'notes': 'Initial meter assigned on account creation.',
                })
        return partners

    def write(self, vals):
        if 'meter_number' not in vals:
            return super().write(vals)

        new_meter = vals.get('meter_number')

        for partner in self:
            old_meter = partner.meter_number

            # Same value - nothing to do
            if old_meter == new_meter:
                continue

            active_histories = self.env['meter.history'].search([
                ('partner_id', '=', partner.id),
                ('state', '=', 'active'),
            ])

            if old_meter:
                # This is a genuine swap - an existing meter is being replaced
                if active_histories and active_histories.final_reading == 0.0:
                    raise UserError(_(
                        "Enter the final reading on %(partner)s's active meter "
                        "history record (Meter History menu) before changing "
                        "the meter number.",
                        partner=partner.display_name,
                    ))
                if active_histories:
                    active_histories.write({
                        'state': 'replaced',
                        'end_date': fields.Date.today(),
                        'notes': f'Replaced by {new_meter}' if new_meter else 'Meter removed',
                    })
            else:
                # No previous meter on file - if a stale active history
                # somehow exists without a meter_number match, close it out
                # too, so we never end up with two active rows for one partner.
                if active_histories:
                    active_histories.write({
                        'state': 'replaced',
                        'end_date': fields.Date.today(),
                        'notes': 'Closed out - superseded by new meter assignment.',
                    })

            if new_meter:
                self.env['meter.history'].create({
                    'partner_id': partner.id,
                    'meter_number': new_meter,
                    'account_number': partner.account_number,
                    'state': 'active',
                    'notes': (f'Meter updated from {old_meter}' if old_meter
                              else 'Meter assigned (customer previously had none on file).'),
                })

        return super().write(vals)

    def action_sync_meter_history(self):
        partners = self.search([('meter_number', '!=', False)])
        created_count = 0
        for partner in partners:
            existing = self.env['meter.history'].search([
                ('partner_id', '=', partner.id),
                ('meter_number', '=', partner.meter_number)
            ], limit=1)
            if not existing:
                self.env['meter.history'].create({
                    'partner_id': partner.id,
                    'meter_number': partner.meter_number,
                    'account_number': partner.account_number,
                    'state': 'active',
                    'notes': 'Backfilled from existing customer profile.'
                })
                created_count += 1

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Meter Sync Complete',
                'message': f'Successfully generated history for {created_count} customer(s).',
                'sticky': False,
            }
        }
