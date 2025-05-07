# management/commands/recalculate_stock.py
from django.core.management.base import BaseCommand
from ...utils import recalculate_all_activity_product_stock

class Command(BaseCommand):
    help = 'Recalculate stock for all activity products based on component availability'

    def handle(self, *args, **options):
        updated_count = recalculate_all_activity_product_stock()
        self.stdout.write(
            self.style.SUCCESS(f'Successfully updated stock for {updated_count} activity products')
        )