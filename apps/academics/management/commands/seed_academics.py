from django.core.management.base import BaseCommand
from apps.academics.models import Class, Section


CLASS_SECTIONS = {
    "Nursery": 2,
    "KG": 2,
    "Grade 1": 2,
    "Grade 2": 2,
    "Grade 3": 2,
    "Grade 4": 2,
    "Grade 5": 2,
    "Grade 6": 2,
    "Grade 7": 2,
    "Grade 8": 2,
    "Grade 9": 2,
    "Grade 10": 2,
    "Grade 11": 2,
    "Grade 12": 2,
}


class Command(BaseCommand):
    help = "Seed default Class and Section records so registration dropdowns have data."

    def handle(self, *args, **options):
        created_classes = 0
        created_sections = 0

        for idx, (cls_name, num_sections) in enumerate(CLASS_SECTIONS.items(), start=1):
            cls, cls_created = Class.objects.get_or_create(
                name=cls_name, defaults={"code": f"CLS{idx:03d}"}
            )
            if cls_created:
                created_classes += 1

            for i in range(1, num_sections + 1):
                sec_name = chr(ord("A") + i - 1)
                _, sec_created = Section.objects.get_or_create(
                    name=sec_name, class_obj=cls
                )
                if sec_created:
                    created_sections += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"Seeded {created_classes} classes and {created_sections} sections."
            )
        )
