# Copyright (C) 2014 Andrey Antukh <niwi@niwi.be>
# Copyright (C) 2014 Jesús Espino <jespinog@gmail.com>
# Copyright (C) 2014 David Barragán <bameda@dbarragan.com>
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as
# published by the Free Software Foundation, either version 3 of the
# License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

import json
from django.apps import apps
from rest_framework import serializers

from taiga.base.serializers import Serializer, PickleField, NeighborsSerializerMixin
from taiga.mdrender.service import render as mdrender
from taiga.projects.validators import ProjectExistsValidator, UserStoryStatusExistsValidator
from taiga.projects.userstories.validators import UserStoryExistsValidator
from taiga.projects.notifications.validators import WatchersValidator

from . import models


class RolePointsField(serializers.WritableField):
    def to_native(self, obj):
        return {str(o.role.id): o.points.id for o in obj.all()}

    def from_native(self, obj):
        if isinstance(obj, dict):
            return obj
        return json.loads(obj)


class UserStorySerializer(WatchersValidator, serializers.ModelSerializer):
    tags = PickleField(default=[], required=False)
    points = RolePointsField(source="role_points", required=False)
    total_points = serializers.SerializerMethodField("get_total_points")
    comment = serializers.SerializerMethodField("get_comment")
    milestone_slug = serializers.SerializerMethodField("get_milestone_slug")
    milestone_name = serializers.SerializerMethodField("get_milestone_name")
    origin_issue = serializers.SerializerMethodField("get_origin_issue")
    blocked_note_html = serializers.SerializerMethodField("get_blocked_note_html")
    description_html = serializers.SerializerMethodField("get_description_html")

    class Meta:
        model = models.UserStory
        depth = 0
        read_only_fields = ('created_date', 'modified_date')

    def get_total_points(self, obj):
        return obj.get_total_points()

    def get_comment(self, obj):
        # NOTE: This method and field is necessary to historical comments work
        return ""

    def get_milestone_slug(self, obj):
        if obj.milestone:
            return obj.milestone.slug
        else:
            return None

    def get_milestone_name(self, obj):
        if obj.milestone:
            return obj.milestone.name
        else:
            return None

    def get_origin_issue(self, obj):
        if obj.generated_from_issue:
            return {
                "id": obj.generated_from_issue.id,
                "ref": obj.generated_from_issue.ref,
                "subject": obj.generated_from_issue.subject,
            }
        return None

    def get_blocked_note_html(self, obj):
        return mdrender(obj.project, obj.blocked_note)

    def get_description_html(self, obj):
        return mdrender(obj.project, obj.description)


class UserStoryNeighborsSerializer(NeighborsSerializerMixin, UserStorySerializer):

    def serialize_neighbor(self, neighbor):
        return NeighborUserStorySerializer(neighbor).data


class NeighborUserStorySerializer(serializers.ModelSerializer):
    class Meta:
        model = models.UserStory
        fields = ("id", "ref", "subject")
        depth = 0


class UserStoriesBulkSerializer(ProjectExistsValidator, UserStoryStatusExistsValidator,
                                Serializer):
    project_id = serializers.IntegerField()
    status_id = serializers.IntegerField(required=False)
    bulk_stories = serializers.CharField()


## Order bulk serializers

class _UserStoryOrderBulkSerializer(UserStoryExistsValidator, Serializer):
    us_id = serializers.IntegerField()
    order = serializers.IntegerField()


class UpdateUserStoriesOrderBulkSerializer(ProjectExistsValidator,
                                                 UserStoryStatusExistsValidator,
                                                 Serializer):
    project_id = serializers.IntegerField()
    bulk_stories = _UserStoryOrderBulkSerializer(many=True)
