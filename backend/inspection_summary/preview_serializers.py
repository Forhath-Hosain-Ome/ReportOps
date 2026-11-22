"""Explicit outward contract; ratios are finite numbers, missing values null."""
from rest_framework import serializers as s
from .serializers import JobSerializer


class DefectSerializer(s.Serializer):
    ordinal = s.IntegerField(required=False)
    occurrence = s.IntegerField(required=False)
    source_number = s.IntegerField(allow_null=True, required=False)
    category = s.CharField(allow_null=True)
    label = s.CharField()


class RankSerializer(s.Serializer):
    rank = s.IntegerField()
    quantity = s.IntegerField()
    ratio = s.FloatField(allow_null=True)
    defects = DefectSerializer(many=True)


class ManpowerEntrySerializer(s.Serializer):
    date = s.DateField()
    values = s.ListField(child=s.CharField(allow_null=True))


class ManpowerSerializer(s.Serializer):
    days = s.IntegerField()
    aggregate_persons = s.IntegerField(allow_null=True)
    entries = ManpowerEntrySerializer(many=True)


class BlockSerializer(s.Serializer):
    id = s.CharField()
    report_type = s.CharField()
    title = s.CharField()
    kind = s.CharField()
    empty = s.BooleanField()
    source_position = s.IntegerField()
    factory_names = s.ListField(child=s.CharField())
    date_start = s.DateField(allow_null=True)
    date_end = s.DateField(allow_null=True)
    inspection_days = s.IntegerField(allow_null=True)
    count = s.IntegerField(allow_null=True)
    count_kind = s.CharField()
    shipment_qty = s.IntegerField(allow_null=True)
    inspected_qty = s.IntegerField(allow_null=True)
    pass_qty = s.IntegerField(allow_null=True)
    defect_qty = s.IntegerField(allow_null=True)
    defect_ratio = s.FloatField(allow_null=True)
    items = s.ListField(child=s.CharField())
    team_leader = s.CharField(allow_null=True)
    top_defects = RankSerializer(many=True)
    manpower = ManpowerSerializer(required=False)


class TeamSerializer(s.Serializer):
    duration_days = s.IntegerField(allow_null=True)
    inspected_qty = s.IntegerField(allow_null=True)
    defect_qty = s.IntegerField(allow_null=True)
    defect_ratio = s.FloatField(allow_null=True)
    top_defects = RankSerializer(many=True)
    style_count = s.IntegerField(allow_null=True, required=False)
    passed_qty = s.IntegerField(allow_null=True, required=False)
    audit_count = s.IntegerField(allow_null=True, required=False)
    shipment_qty = s.IntegerField(allow_null=True, required=False)


class ComparisonSerializer(s.Serializer):
    ratio_reduction = s.FloatField(allow_null=True)
    inspection_factor = s.FloatField(allow_null=True)
    equivalent_findings = s.CharField(allow_null=True)
    equivalent_calculation = s.CharField(allow_null=True)


class DashboardSerializer(s.Serializer):
    matched_styles = s.ListField(child=s.CharField())
    matched_style_count = s.IntegerField()
    final_available = s.BooleanField()
    team_100 = TeamSerializer()
    final = TeamSerializer()
    comparison = ComparisonSerializer()


class ManifestSerializer(s.Serializer):
    id = s.CharField()
    name = s.CharField()
    source_position = s.IntegerField()
    position = s.IntegerField()
    kind = s.CharField()
    empty = s.BooleanField()


class OverviewSerializer(s.Serializer):
    blocks = ManifestSerializer(many=True)
    sections = s.ListField(child=s.CharField())
    generation_status = s.CharField()
    reconciliation_status = s.CharField()


class DetailColumnSerializer(s.Serializer):
    kind = s.CharField()
    ordinal = s.IntegerField(allow_null=True)
    occurrence = s.IntegerField(allow_null=True)
    source_number = s.IntegerField(allow_null=True, required=False)
    category = s.CharField(allow_null=True)
    key = s.CharField()
    label = s.CharField(allow_blank=True)
    group = s.CharField(allow_null=True)
    number = s.IntegerField(allow_null=True)


class DetailRowSerializer(s.Serializer):
    kind = s.ChoiceField(choices=["detail", "subtotal", "total"])
    values = s.DictField(child=s.JSONField())


class DetailSerializer(s.Serializer):
    columns = DetailColumnSerializer(many=True)
    rows = DetailRowSerializer(many=True)
    record_count = s.IntegerField()


class ReconciliationSerializer(s.Serializer):
    inspection_qty = s.IntegerField(allow_null=True)
    pass_qty = s.IntegerField(allow_null=True)
    defect_qty = s.IntegerField(allow_null=True)
    defect_category_total = s.IntegerField()
    defect_field_count = s.IntegerField()
    defect_category_count = s.IntegerField()
    hundred_percent_format = s.CharField(allow_null=True)
    record_count = s.IntegerField()
    inspection_day_count = s.IntegerField()
    style_count = s.IntegerField()
    status = s.CharField()
    inspection_matches_detail = s.BooleanField()
    pass_matches_detail = s.BooleanField()
    defect_matches_categories = s.BooleanField()
    record_count_valid = s.BooleanField()


class AvailabilitySerializer(s.Serializer):
    qc_dashboard = s.BooleanField()
    analysis = s.BooleanField()
    summary = s.BooleanField()
    detail_100 = s.BooleanField()


class SourcesSerializer(s.Serializer):
    inspection_summary = s.BooleanField()
    hundred_percent = s.BooleanField()
    hundred_percent_format = s.CharField(allow_null=True)


class PreviewSerializer(s.Serializer):
    available_sections = AvailabilitySerializer()
    sources = SourcesSerializer()
    job = JobSerializer()
    overview = OverviewSerializer()
    dashboard = DashboardSerializer(allow_null=True)
    analysis = BlockSerializer(many=True)
    summary = BlockSerializer(many=True)
    detail = DetailSerializer(allow_null=True)
    reconciliation = ReconciliationSerializer(allow_null=True)
