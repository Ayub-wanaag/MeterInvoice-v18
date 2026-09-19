from odoo import models, fields, api


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    is_water = fields.Boolean(string='Is Water Product')

    water_tier_ids = fields.Many2many(
        'customer.category',
        string='Billing Categories',
        compute='_compute_water_tiers'
    )

    @api.depends('is_water')
    def _compute_water_tiers(self):
        categories = self.env['customer.category'].sudo().search(
            [], order='name'
        )
        for product in self:
            if product.is_water:
                product.water_tier_ids = categories
            else:
                product.water_tier_ids = False
