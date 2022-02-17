# -*- coding: utf-8 -*-
# © 2014-2016 Akretion (http://www.akretion.com)
# @author Alexis de Lattre <alexis.delattre@akretion.com>
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from odoo import models, fields, api, _
import logging

logger = logging.getLogger(__name__)


class StockInventory(models.Model):
    _inherit = 'stock.inventory'
    _order = 'id desc'


class StockInventoryLine(models.Model):
    _inherit = 'stock.inventory.line'

    inventory_id = fields.Many2one(states={'done': [('readonly', True)]})
    inventory_date = fields.Datetime(
        related='inventory_id.date', readonly=True)
    partner_id = fields.Many2one(states={'done': [('readonly', True)]})
    product_id = fields.Many2one(states={'done': [('readonly', True)]})
    product_code = fields.Char(readonly=True, compute_sudo=True)
    product_uom_id = fields.Many2one(states={'done': [('readonly', True)]})
    product_qty = fields.Float(states={'done': [('readonly', True)]})
    location_id = fields.Many2one(states={'done': [('readonly', True)]})
    location_name = fields.Char(readonly=True, compute_sudo=True)
    package_id = fields.Many2one(states={'done': [('readonly', True)]})
    prod_lot_id = fields.Many2one(states={'done': [('readonly', True)]})
    state = fields.Selection(store=True)
    inventory_location_id = fields.Many2one(readonly=True)
    product_name = fields.Char(compute_sudo=True)
    prodlot_name = fields.Char(compute_sudo=True)


class StockPicking(models.Model):
    _inherit = 'stock.picking'
    _order = 'id desc'
    # In the stock module: _order = "priority desc, date asc, id desc"
    # The problem is date asc

    partner_id = fields.Many2one(track_visibility='onchange')
    picking_type_id = fields.Many2one(track_visibility='onchange')
    move_type = fields.Selection(track_visibility='onchange')

    @api.multi
    def force_assign(self):
        res = super(StockPicking, self).force_assign()
        for pick in self:
            pick.message_post(_("Using <b>Force Availability</b>!"))
        return res

    @api.multi
    def do_unreserve(self):
        res = super(StockPicking, self).do_unreserve()
        for pick in self:
            pick.message_post(_("Picking <b>unreserved</b>."))
        return res


class StockLocation(models.Model):
    _inherit = 'stock.location'

    name = fields.Char(translate=False)
    # with the 'quant_ids' field below, you can for example search empty stock
    # locations with self.env['stock.location'].search([
    #    ('child_ids', '=', False), ('quant_ids', '=', False),
    #    ('usage', '=', 'internal')])
    quant_ids = fields.One2many(
        'stock.quant', 'location_id', string="Related Quants")


class StockPickingType(models.Model):
    _inherit = 'stock.picking.type'

    name = fields.Char(translate=False)


class StockLocationRoute(models.Model):
    _inherit = 'stock.location.route'

    name = fields.Char(translate=False)


class StockWarehouseOrderpoint(models.Model):
    _inherit = 'stock.warehouse.orderpoint'

    # This is for the button shortcut "reordering rules" on
    # stock.location form view, so that the location_id has the
    # good value, not the default stock location of the first WH of the company
    @api.model
    def default_get(self, fields):
        if self._context.get('default_location_id'):
            location = self.env['stock.location'].browse(
                self._context['default_location_id'])
            wh = location.get_warehouse()
            if location and wh:
                self = self.with_context(default_warehouse_id=wh.id)
        return super(StockWarehouseOrderpoint, self).default_get(fields)

    # This SQL constraint blocks the use of the "active" field
    # but I think it's not very useful to have such an "active" field
    # on orderpoints ; when you think the order point is bad, you update
    # the min/max values, you don't de-active it !
    _sql_constraints = [(
        'company_wh_location_product_unique',
        'unique(company_id, warehouse_id, location_id, product_id)',
        'An orderpoint already exists for the same company, same warehouse, '
        'same stock location and same product.'
        )]


class StockMove(models.Model):
    _inherit = 'stock.move'

# It seems that it is not necessary any more to
# have the digits= on these 2 fields to fix the bug
# https://github.com/odoo/odoo/pull/10038
#    reserved_availability = fields.Float(
#        digits=dp.get_precision('Product Unit of Measure'))
#    availability = fields.Float(
#        digits=dp.get_precision('Product Unit of Measure'))

    @api.multi
    def name_get(self):
        '''name_get of stock_move is important for the reservation of the
        quants: so want to add the name of the customer and the expected date
        in it'''
        res = []
        for line in self:
            name = line.location_id.name + ' > ' + line.location_dest_id.name
            if line.product_id.code:
                name = line.product_id.code + ': ' + name
            if line.picking_id.origin:
                name = line.picking_id.origin + ' ' + name
            if line.partner_id:
                name = line.partner_id.name + ' ' + name
            if line.date_expected:
                name = name + ' ' + line.date_expected
            res.append((line.id, name))
        return res

    def button_do_unreserve(self):
        for move in self:
            move.do_unreserve()
            if move.picking_id:
                product = move.product_id
                self.picking_id.message_post(_(
                    "Product <a href=# data-oe-model=product.product "
                    "data-oe-id=%d>%s</a> qty %s %s <b>unreserved</b>")
                    % (product.id, product.display_name,
                       move.product_qty, move.product_id.uom_id.name))
            ops = self.env['stock.pack.operation']
            for smol in move.linked_move_operation_ids:
                if smol.operation_id:
                    ops += smol.operation_id
            ops.unlink()


class StockIncoterms(models.Model):
    _inherit = 'stock.incoterms'

    @api.multi
    def name_get(self):
        res = []
        for inco in self:
            res.append((inco.id, u'[%s] %s' % (inco.code, inco.name)))
        return res


class StockQuant(models.Model):
    _inherit = 'stock.quant'

    @api.model
    def _cron_auto_unpack_on_internal_locations(self):
        # Problem in v10: when you manage packs in Odoo for customer pickings,
        # you have the following problem: when you return a customer picking,
        # if you return all the products that were in the same pack, the pack
        # is returned, so you have in your stock one or several quants
        # inside a pack. This is a problem when you want to ship those
        # products again.
        # I provide the code in this module, but not the cron, because in some
        # scenarios, you may want to have packs in your stock.
        # Just add the cron in the specific module of your project.
        # Underlying problem solved in Odoo v11. Don't port that to v14 !
        logger.info('START cron auto unpack on internal locations')
        int_locs = self.env['stock.location'].search([('usage', '=', 'internal')])
        quants = self.search([
            ('location_id', 'in', int_locs.ids),
            ('package_id', '!=', False)])
        packages = quants.mapped('package_id')
        logger.info('Unpacking %d packages on internal locations', len(packages))
        packages.unpack()
        logger.info('END cron auto unpack on internal locations')


class ProcurementGroup(models.Model):
    _inherit = 'procurement.group'

    picking_ids = fields.One2many(
        'stock.picking', 'group_id', string='Pickings', readonly=True)
