from odoo import models, fields, api


class CustomerCategory(models.Model):
    _name = 'customer.category'
    _description = 'Customer Billing Category'
    _order = 'name'

    name = fields.Char(
        string='Category Name',
        required=True
    )
    
    # Compute field to dynamically hide/show tabs in views
    is_bh = fields.Boolean(
        string='Is Borehole Category',
        compute='_compute_is_bh'
    )

    @api.depends('name')
    def _compute_is_bh(self):
        for record in self:
            if record.name and record.name.strip().endswith('BH'):
                record.is_bh = True
            else:
                record.is_bh = False

    # Separate water tiers
    water_tier_ids = fields.One2many(
        'customer.category.tier',
        'category_id',
        string='Water Tiers',
        domain=[('tier_type', '=', 'water')]
    )

    # Separate sewerage tiers
    sewerage_tier_ids = fields.One2many(
        'customer.category.tier',
        'category_id',
        string='Sewerage Tiers',
        domain=[('tier_type', '=', 'sewerage')]
    )


class CustomerCategoryTier(models.Model):
    _name = 'customer.category.tier'
    _description = 'Category Billing Tier'
    _order = 'from_unit'

    category_id = fields.Many2one(
        'customer.category',
        string='Category',
        required=True,
        ondelete='cascade'
    )

    tier_type = fields.Selection([
        ('water', 'Water'),
        ('sewerage', 'Sewerage'),
    ], string='Type', required=True, default='water')

    from_unit = fields.Integer(
        string='From Unit',
        required=True
    )

    to_unit = fields.Integer(
        string='To Unit',
        help='Use 999999 for unlimited ranges'
    )

    price_per_unit = fields.Integer(
        string='Price per Unit',
        required=True
    )
