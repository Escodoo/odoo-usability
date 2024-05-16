# Copyright 2024 Escodoo - Kaynnan Lemes <kaynnan.lemes@escodoo.com.br>
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
from openupgradelib import openupgrade


@openupgrade.migrate()
def migrate(env, version):
    if not version:
        return
    # Remove registros de tax_definition_product_rel que não estão associados a nenhum produto ou product_template
    if openupgrade.table_exists(env.cr, 'tax_definition_product_rel'):
        env.cr.execute("""
            DELETE FROM tax_definition_product_rel AS tdpr
                WHERE NOT EXISTS (
                SELECT 1
                FROM product_template AS pt
                WHERE pt.id = tdpr.product_id
                )
                AND NOT EXISTS (
                SELECT 1
                FROM product_product AS pp
                WHERE pp.product_tmpl_id = tdpr.product_id
            )
        """)
