"""Temporary smoke test: deleting a student purges face data. Run once, then delete."""

import io
import os

import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "face_attendance.settings")
django.setup()

from django.core.files.uploadedfile import SimpleUploadedFile
from PIL import Image

from apps.accounts.models import StudentProfile, User
from apps.faces.models import FaceEmbedding, FaceImage
from rest_framework.test import APIClient

buf = io.BytesIO()
Image.new("RGB", (60, 60)).save(buf, format="JPEG")
img = SimpleUploadedFile("t.jpg", buf.getvalue(), content_type="image/jpeg")

u = User.objects.get(username="face_api_test")
FaceImage.objects.create(user=u, image=img)
FaceEmbedding.objects.create(user=u, embedding=[0.1] * 512)

sp = StudentProfile.objects.filter(user=u).first()
if sp is None:
    from apps.academics.models import Class
    cls = Class.objects.first()
    sp = StudentProfile.objects.create(user=u, roll_number="TEST-DELETE-1", class_obj=cls)
    print("created temp profile", sp.id)
c = APIClient()
c.force_authenticate(user=User.objects.get(username="admin"))
r = c.delete(f"/api/auth/students/{sp.id}/")
print(r.status_code, getattr(r, "data", None))
print("embeddings left:", FaceEmbedding.objects.filter(user=u).count())
print("images left:", FaceImage.objects.filter(user=u).count())
print("profiles left:", StudentProfile.objects.filter(user=u).count())
print("users left:", User.objects.filter(id=u.id).count())
