# core/utils.py
import os
import uuid

def get_image_filename(instance, filename):
    # Crée un nom de fichier unique (UUID) et préserve l'extension d'origine
    # Exemple: 'abcdef12-3456-7890-abcd-ef1234567890.png'
    image_name = uuid.uuid4().hex[:12] # Prend les 12 premiers caractères de l'UUID
    ext = os.path.splitext(filename)[1]
    return f'modeles_images/{image_name}{ext}'