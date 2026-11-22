# backend/image_processor/serializers/folder_upload_serializer.py
from rest_framework import serializers
import os
from collections import defaultdict
from image_processor.upload_paths import validate_upload_path

MAX_FILE_SIZE = 50 * 1024 * 1024
VALID_IMAGE_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.bmp', '.gif', '.tiff', '.webp'}


class FolderUploadSerializer(serializers.Serializer):
    files = serializers.ListField(
        child=serializers.FileField(max_length=512, allow_empty_file=False, use_url=False),
        allow_empty=False,
        error_messages={"empty": "At least one image file is required."},
    )
    paths = serializers.ListField(
        child=serializers.CharField(max_length=1024),
        allow_empty=True,
        required=False,
        default=list,
        help_text="List of relative paths corresponding to each file."
    )
    style = serializers.CharField(max_length=255, allow_blank=True, required=False, default="")
    is_renamed_file = serializers.BooleanField(required=False, default=False)

    def validate_style(self, value):
        return validate_upload_path(value, single_component=True) if value else value

    def validate(self, data):
        files = data.get('files', [])
        paths = data.get('paths', []) or []
        paths = [p.replace('\\', '/') for p in paths]
        is_renamed_file = data.get('is_renamed_file', [])
        errors = []

        if files and not paths:
            paths = [getattr(f, 'name', '') for f in files]
            data['paths'] = paths

        if len(files) != len(paths):
            raise serializers.ValidationError("The number of files and paths must match.")

        paths = [validate_upload_path(path) for path in paths]
        data['paths'] = paths
        for f, path in zip(files, paths):
            validate_upload_path(f.name, single_component=True)
            ext = os.path.splitext(path)[1].lower()
            if ext not in VALID_IMAGE_EXTENSIONS or os.path.splitext(f.name)[1].lower() not in VALID_IMAGE_EXTENSIONS:
                errors.append(f"{path}: Only image files (JPG, JPEG, PNG, BMP, GIF, TIFF, WEBP) are accepted.")
            if f.size > MAX_FILE_SIZE:
                errors.append(f"{path}: Exceeds the 50 MB limit.")

        if errors:
            raise serializers.ValidationError(errors)

        # ── Normalize filenames to sequential integers per folder ──────────
        # e.g. style...qsp65102_78.jpg  →  01.jpg, 02.jpg, 03.jpg ...
        # Grouped by their parent folder so each folder starts at 01.
        folder_counters = defaultdict(int)
        normalized_paths = []
        if not is_renamed_file:
            for path in paths:
                parts = path.split('/')
                if len(parts) > 1:
                    # has a folder prefix — keep the folder, renumber the file
                    folder = '/'.join(parts[:-1])
                    ext = os.path.splitext(parts[-1])[1].lower() or '.jpg'
                else:
                    folder = ''
                    ext = os.path.splitext(parts[-1])[1].lower() or '.jpg'

                folder_counters[folder] += 1
                seq = folder_counters[folder]
                new_filename = f"{seq:02d}{ext}"
                new_path = f"{folder}/{new_filename}" if folder else new_filename
                normalized_paths.append(new_path)

            data['paths'] = normalized_paths
            return data
        return data
