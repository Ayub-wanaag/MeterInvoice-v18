from odoo import models, fields, api
from odoo.exceptions import ValidationError


class AccountMove(models.Model):
    """ Inheriting the parent Invoice model directly inside account_move_line.py """
    _inherit = 'account.move'

    is_meter_swap_invoice = fields.Boolean(
        string='Meter Swap Invoice', 
        default=False,
        help="Check this box if this specific billing cycle involves a physical meter swap."
    )


class AccountMoveLine(models.Model):
    """ Your core billing line logic """
    _inherit = 'account.move.line'

    previous_reading = fields.Float(string='Previous', default=0.0)
    new_reading = fields.Float(string='New', default=0.0)
    actual_reading = fields.Float(string='Actual', default=0.0, store=True)
    
    # Automatically pulls the swap state from the parent invoice header field
    is_meter_swap = fields.Boolean(
        string='Meter Swap', 
        related='move_id.is_meter_swap_invoice', 
        store=True
    )
    
    # Boss's tracking fields for revenue protection
    old_meter_final = fields.Float(string='Old Meter Final Reading', default=0.0)
    new_meter_start = fields.Float(string='New Meter Initial Reading', default=0.0)
    
    water_cost = fields.Float(string='Water Cost', default=0.0, store=True)
    sewerage_cost = fields.Float(string='Sewerage Cost', default=0.0, store=True)
    total_amount = fields.Float(string='Total Amount', default=0.0, store=True)

    def _get_tier_total(self, consumption, tier_type='water'):
        partner = self.move_id.partner_id
        category = partner.customer_category_id if partner else False

        if not category:
            return 0.0

        if tier_type == 'water':
            tiers = category.water_tier_ids.sorted('from_unit')
        else:
            tiers = category.sewerage_tier_ids.sorted('from_unit')

        if not tiers:
            return 0.0

        total = 0.0
        remaining = float(consumption)

        for tier in tiers:
            if remaining <= 0:
                break
            tier_capacity = tier.to_unit - tier.from_unit + 1
            units_in_tier = min(remaining, tier_capacity)
            if units_in_tier > 0:
                total += units_in_tier * tier.price_per_unit
                remaining -= units_in_tier

        return total

    def _calculate_line_metrics(self):
        """ Computes consumption metrics dynamically from the interface fields """
        for line in self:
            if line.is_meter_swap:
                # Calculate consumption from previous old meter before extraction
                old_consumption = max(line.old_meter_final - line.previous_reading, 0.0)
                # Calculate consumption from fresh new meter since installation
                new_consumption = max(line.new_reading - line.new_meter_start, 0.0)
                # Combined total consumption
                line.actual_reading = old_consumption + new_consumption
            else:
                # Standard single meter math
                actual = line.new_reading - line.previous_reading
                line.actual_reading = max(actual, 0.0)
            
            if line.actual_reading > 0:
                line.quantity = int(line.actual_reading)
                if line.product_id.is_water:
                    partner = line.move_id.partner_id
                    category = partner.customer_category_id if partner else False
                    
                    is_bh = False
                    if category and category.name and category.name.strip().endswith('BH'):
                        is_bh = True

                    if is_bh:
                        water = 0.0
                        sewerage = line._get_tier_total(line.actual_reading, 'sewerage')
                    else:
                        water = line._get_tier_total(line.actual_reading, 'water')
                        sewerage_units = line.actual_reading * 0.75
                        sewerage = line._get_tier_total(sewerage_units, 'sewerage')
                        
                    line.water_cost = water
                    line.sewerage_cost = sewerage
                    line.total_amount = water + sewerage
                    line.price_unit = line.total_amount / line.actual_reading
            else:
                line.quantity = 0.0
                line.water_cost = 0.0
                line.sewerage_cost = 0.0
                line.total_amount = 0.0
                if line.actual_reading == 0.0:
                    line.price_unit = 0.0

    def _validate_water_category(self):
        for line in self:
            if line.product_id.is_water:
                partner = line.move_id.partner_id
                if not partner.customer_category_id:
                    raise ValidationError(
                        f"Customer '{partner.name}' does not have a "
                        f"billing category assigned.\n"
                        f"Please go to the customer form and assign "
                        f"a category before saving this invoice."
                    )
                category = partner.customer_category_id
                
                is_bh = False
                if category.name and category.name.strip().endswith('BH'):
                    is_bh = True
                    
                if is_bh:
                    if not category.sewerage_tier_ids:
                        raise ValidationError(
                            f"Borehole Category '{category.name}' has no sewerage "
                            f"tiers configured.\n"
                            f"Please add sewerage tiers to this category first."
                        )
                else:
                    if not category.water_tier_ids:
                        raise ValidationError(
                            f"Category '{category.name}' has no water "
                            f"tiers configured.\n"
                            f"Please add water tiers to this category first."
                        )
                
                # Validation checks for reading inputs to stop logical typos
                if line.is_meter_swap:
                    if line.old_meter_final < line.previous_reading:
                        raise ValidationError(f"Validation Error: Old Meter Final Reading ({line.old_meter_final}) cannot be less than its Starting Reading ({line.previous_reading}).")
                    if line.new_reading < line.new_meter_start:
                        raise ValidationError(f"Validation Error: New Meter Current Reading ({line.new_reading}) cannot be less than its Initial Starting Reading ({line.new_meter_start}).")
                else:
                    if line.new_reading < line.previous_reading:
                        raise ValidationError(f"The new meter reading ({line.new_reading}) cannot be less than the previous reading ({line.previous_reading}). If a meter swap took place, please check the main 'Meter Swap Invoice' box.")

    def _get_previous_reading(self):
        self.ensure_one()
        partner = self.move_id.partner_id
        product = self.product_id
        if not partner or not product:
            return 0.0
        current_id = self.move_id.id if isinstance(self.move_id.id, int) else False
        domain = [
            ('partner_id', '=', partner.id),
            ('move_type', '=', 'out_invoice'),
            ('state', '=', 'posted'),
        ]
        if current_id:
            domain.append(('id', '!=', current_id))
        previous_invoice = self.env['account.move'].search(
            domain,
            order='invoice_date desc, id desc',
            limit=1
        )
        if not previous_invoice:
            return 0.0
        previous_line = previous_invoice.invoice_line_ids.filtered(
            lambda l: l.product_id.id == product.id
        )
        return previous_line[:1].new_reading if previous_line else 0.0

    @api.onchange('product_id', 'move_id.partner_id')
    def _onchange_product_or_partner(self):
        """ Default system lookup kicks in on item selection """
        for line in self:
            if line.product_id and line.move_id.partner_id and not line.is_meter_swap:
                line.previous_reading = line._get_previous_reading()

    @api.onchange('is_meter_swap')
    def _onchange_is_meter_swap(self):
        """ Handles field adjustments when the swap execution token changes state """
        for line in self:
            if not line.is_meter_swap:
                line.old_meter_final = 0.0
                line.new_meter_start = 0.0
                line.previous_reading = line._get_previous_reading()
            self._calculate_line_metrics()

    @api.onchange('new_reading', 'previous_reading', 'old_meter_final', 'new_meter_start')
    def _onchange_readings(self):
        self._calculate_line_metrics()

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if 'product_id' in vals and 'previous_reading' not in vals:
                move = self.env['account.move'].browse(vals.get('move_id'))
                product = self.env['product.product'].browse(vals.get('product_id'))
                if move and product:
                    domain = [
                        ('partner_id', '=', move.partner_id.id),
                        ('move_type', '=', 'out_invoice'),
                        ('state', '=', 'posted'),
                    ]
                    prev_inv = self.env['account.move'].search(domain, order='invoice_date desc, id desc', limit=1)
                    if prev_inv:
                        prev_line = prev_inv.invoice_line_ids.filtered(lambda l: l.product_id.id == product.id)
                        vals['previous_reading'] = prev_line[:1].new_reading if prev_line else 0.0

        records = super().create(vals_list)
        records._validate_water_category()
        records._calculate_line_metrics()
        return records

    def write(self, vals):
        res = super().write(vals)
        if any(k in vals for k in ['new_reading', 'previous_reading', 'product_id', 'is_meter_swap', 'old_meter_final', 'new_meter_start']):
            self._validate_water_category()
            self._calculate_line_metrics()
        return res
