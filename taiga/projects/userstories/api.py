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

from contextlib import suppress

from django.apps import apps
from django.db import transaction
from django.utils.translation import ugettext as _
from django.shortcuts import get_object_or_404
from django.core.exceptions import ObjectDoesNotExist

from rest_framework.response import Response
from rest_framework import status

from taiga.base import filters, response
from taiga.base import exceptions as exc
from taiga.base.decorators import list_route
from taiga.base.api import ModelCrudViewSet

from taiga.projects.notifications.mixins import WatchedResourceMixin
from taiga.projects.history.mixins import HistoryResourceMixin
from taiga.projects.occ import OCCResourceMixin

from taiga.projects.models import Project, UserStoryStatus
from taiga.projects.history.services import take_snapshot

from . import models
from . import permissions
from . import serializers
from . import services


class UserStoryViewSet(OCCResourceMixin, HistoryResourceMixin, WatchedResourceMixin, ModelCrudViewSet):
    model = models.UserStory
    serializer_class = serializers.UserStoryNeighborsSerializer
    list_serializer_class = serializers.UserStorySerializer
    permission_classes = (permissions.UserStoryPermission,)

    filter_backends = (filters.CanViewUsFilterBackend, filters.TagsFilter,
                       filters.QFilter)
    retrieve_exclude_filters = (filters.TagsFilter,)
    filter_fields = ['project', 'milestone', 'milestone__isnull', 'status', 'is_archived']

    # Specific filter used for filtering neighbor user stories
    _neighbor_tags_filter = filters.TagsFilter('neighbor_tags')

    def get_queryset(self):
        qs = self.model.objects.all()
        qs = qs.prefetch_related("points",
                                 "role_points",
                                 "role_points__points",
                                 "role_points__role")
        qs = qs.select_related("milestone", "project")
        return qs

    def pre_save(self, obj):
        # This is very ugly hack, but having
        # restframework is the only way to do it.
        # NOTE: code moved as is from serializer
        # to api because is not serializer logic.
        related_data = getattr(obj, "_related_data", {})
        self._role_points = related_data.pop("role_points", None)

        if not obj.id:
            obj.owner = self.request.user

        super().pre_save(obj)

    def post_save(self, obj, created=False):
        # Code related to the hack of pre_save method. Rather,
        # this is the continuation of it.

        Points = apps.get_model("projects", "Points")
        RolePoints = apps.get_model("userstories", "RolePoints")

        if self._role_points:
            with suppress(ObjectDoesNotExist):
                for role_id, points_id in self._role_points.items():
                    role_points = RolePoints.objects.get(role__id=role_id, user_story_id=obj.pk)
                    role_points.points = Points.objects.get(id=points_id, project_id=obj.project_id)
                    role_points.save()

        super().post_save(obj, created)

    @list_route(methods=["POST"])
    def bulk_create(self, request, **kwargs):
        serializer = serializers.UserStoriesBulkSerializer(data=request.DATA)
        if serializer.is_valid():
            data = serializer.data
            project = Project.objects.get(id=data["project_id"])
            self.check_permissions(request, 'bulk_create', project)
            user_stories = services.create_userstories_in_bulk(
                data["bulk_stories"], project=project, owner=request.user,
                status_id=data.get("status_id") or project.default_us_status_id,
                callback=self.post_save, precall=self.pre_save)
            user_stories_serialized = self.serializer_class(user_stories, many=True)
            return response.Ok(user_stories_serialized.data)
        return response.BadRequest(serializer.errors)

    @list_route(methods=["POST"])
    def bulk_update_backlog_order(self, request, **kwargs):
        serializer = serializers.UpdateUserStoriesOrderBulkSerializer(data=request.DATA)
        if not serializer.is_valid():
            return response.BadRequest(serializer.errors)

        data = serializer.data
        project = get_object_or_404(Project, pk=data["project_id"])

        self.check_permissions(request, "bulk_update_order", project)
        services.update_userstories_order_in_bulk(data["bulk_stories"],
                                                  project=project,
                                                  field="backlog_order")
        services.snapshot_userstories_in_bulk(data["bulk_stories"], request.user)

        return response.NoContent()

    @list_route(methods=["POST"])
    def bulk_update_sprint_order(self, request, **kwargs):
        serializer = serializers.UpdateUserStoriesOrderBulkSerializer(data=request.DATA)
        if not serializer.is_valid():
            return response.BadRequest(serializer.errors)

        data = serializer.data
        project = get_object_or_404(Project, pk=data["project_id"])

        self.check_permissions(request, "bulk_update_order", project)
        services.update_userstories_order_in_bulk(data["bulk_stories"],
                                                  project=project,
                                                  field="sprint_order")
        services.snapshot_userstories_in_bulk(data["bulk_stories"], request.user)
        return response.NoContent()

    @list_route(methods=["POST"])
    def bulk_update_kanban_order(self, request, **kwargs):
        serializer = serializers.UpdateUserStoriesOrderBulkSerializer(data=request.DATA)
        if not serializer.is_valid():
            return response.BadRequest(serializer.errors)

        data = serializer.data
        project = get_object_or_404(Project, pk=data["project_id"])

        self.check_permissions(request, "bulk_update_order", project)
        services.update_userstories_order_in_bulk(data["bulk_stories"],
                                                  project=project,
                                                  field="kanban_order")
        services.snapshot_userstories_in_bulk(data["bulk_stories"], request.user)
        return response.NoContent()

    @transaction.atomic
    def create(self, *args, **kwargs):
        response = super().create(*args, **kwargs)

        # Added comment to the origin (issue)
        if response.status_code == status.HTTP_201_CREATED and self.object.generated_from_issue:
            self.object.generated_from_issue.save()

            comment = _("Generating the user story [US #{ref} - "
                        "{subject}](:us:{ref} \"US #{ref} - {subject}\")")
            comment = comment.format(ref=self.object.ref, subject=self.object.subject)
            history = take_snapshot(self.object.generated_from_issue,
                                    comment=comment,
                                    user=self.request.user)

            self.send_notifications(self.object.generated_from_issue, history)

        return response
