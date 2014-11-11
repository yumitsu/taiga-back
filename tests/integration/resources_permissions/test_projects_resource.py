from django.core.urlresolvers import reverse
from django.apps import apps

from taiga.base.utils import json
from taiga.projects.serializers import ProjectDetailSerializer
from taiga.permissions.permissions import MEMBERS_PERMISSIONS

from tests import factories as f
from tests.utils import helper_test_http_method, helper_test_http_method_and_count

import pytest
pytestmark = pytest.mark.django_db


@pytest.fixture
def data():
    m = type("Models", (object,), {})
    m.registered_user = f.UserFactory.create()
    m.project_member_with_perms = f.UserFactory.create()
    m.project_member_without_perms = f.UserFactory.create()
    m.project_owner = f.UserFactory.create()
    m.other_user = f.UserFactory.create()
    m.superuser = f.UserFactory.create(is_superuser=True)

    m.public_project = f.ProjectFactory(is_private=False,
                                        anon_permissions=['view_project'],
                                        public_permissions=['view_project'])
    m.private_project1 = f.ProjectFactory(is_private=True,
                                          anon_permissions=['view_project'],
                                          public_permissions=['view_project'],
                                          owner=m.project_owner)
    m.private_project2 = f.ProjectFactory(is_private=True,
                                          anon_permissions=[],
                                          public_permissions=[],
                                          owner=m.project_owner)

    f.RoleFactory(project=m.public_project)

    m.membership = f.MembershipFactory(project=m.private_project1,
                                       user=m.project_member_with_perms,
                                       role__project=m.private_project1,
                                       role__permissions=list(map(lambda x: x[0], MEMBERS_PERMISSIONS)))
    m.membership = f.MembershipFactory(project=m.private_project1,
                                       user=m.project_member_without_perms,
                                       role__project=m.private_project1,
                                       role__permissions=[])
    m.membership = f.MembershipFactory(project=m.private_project2,
                                       user=m.project_member_with_perms,
                                       role__project=m.private_project2,
                                       role__permissions=list(map(lambda x: x[0], MEMBERS_PERMISSIONS)))
    m.membership = f.MembershipFactory(project=m.private_project2,
                                       user=m.project_member_without_perms,
                                       role__project=m.private_project2,
                                       role__permissions=[])

    ContentType = apps.get_model("contenttypes", "ContentType")
    Project = apps.get_model("projects", "Project")

    project_ct = ContentType.objects.get_for_model(Project)

    f.VoteFactory(content_type=project_ct, object_id=m.public_project.pk, user=m.project_member_with_perms)
    f.VoteFactory(content_type=project_ct, object_id=m.public_project.pk, user=m.project_owner)
    f.VoteFactory(content_type=project_ct, object_id=m.private_project1.pk, user=m.project_member_with_perms)
    f.VoteFactory(content_type=project_ct, object_id=m.private_project1.pk, user=m.project_owner)
    f.VoteFactory(content_type=project_ct, object_id=m.private_project2.pk, user=m.project_member_with_perms)
    f.VoteFactory(content_type=project_ct, object_id=m.private_project2.pk, user=m.project_owner)

    f.VotesFactory(content_type=project_ct, object_id=m.public_project.pk, count=2)
    f.VotesFactory(content_type=project_ct, object_id=m.private_project1.pk, count=2)
    f.VotesFactory(content_type=project_ct, object_id=m.private_project2.pk, count=2)

    return m


def test_project_retrieve(client, data):
    public_url = reverse('projects-detail', kwargs={"pk": data.public_project.pk})
    private1_url = reverse('projects-detail', kwargs={"pk": data.private_project1.pk})
    private2_url = reverse('projects-detail', kwargs={"pk": data.private_project2.pk})

    users = [
        None,
        data.registered_user,
        data.project_member_with_perms,
        data.project_owner
    ]

    results = helper_test_http_method(client, 'get', public_url, None, users)
    assert results == [200, 200, 200, 200]
    results = helper_test_http_method(client, 'get', private1_url, None, users)
    assert results == [200, 200, 200, 200]
    results = helper_test_http_method(client, 'get', private2_url, None, users)
    assert results == [401, 403, 200, 200]


def test_project_update(client, data):
    url = reverse('projects-detail', kwargs={"pk": data.private_project2.pk})

    project_data = ProjectDetailSerializer(data.private_project2).data
    project_data["is_private"] = False
    project_data = json.dumps(project_data)

    users = [
        None,
        data.registered_user,
        data.project_member_with_perms,
        data.project_owner
    ]

    results = helper_test_http_method(client, 'put', url, project_data, users)
    assert results == [401, 403, 403, 200]


def test_project_delete(client, data):
    url = reverse('projects-detail', kwargs={"pk": data.private_project2.pk})

    users = [
        None,
        data.registered_user,
        data.project_member_with_perms,
        data.project_owner
    ]
    results = helper_test_http_method(client, 'delete', url, None, users)
    assert results == [401, 403, 403, 204]


def test_project_list(client, data):
    url = reverse('projects-list')

    response = client.get(url)
    projects_data = json.loads(response.content.decode('utf-8'))
    assert len(projects_data) == 2
    assert response.status_code == 200

    client.login(data.registered_user)

    response = client.get(url)
    projects_data = json.loads(response.content.decode('utf-8'))
    assert len(projects_data) == 2
    assert response.status_code == 200

    client.login(data.project_member_with_perms)

    response = client.get(url)
    projects_data = json.loads(response.content.decode('utf-8'))
    assert len(projects_data) == 3
    assert response.status_code == 200

    client.login(data.project_owner)

    response = client.get(url)
    projects_data = json.loads(response.content.decode('utf-8'))
    assert len(projects_data) == 3
    assert response.status_code == 200


def test_project_patch(client, data):
    url = reverse('projects-detail', kwargs={"pk": data.private_project2.pk})

    users = [
        None,
        data.registered_user,
        data.project_member_with_perms,
        data.project_owner
    ]
    data = json.dumps({"is_private": False})
    results = helper_test_http_method(client, 'patch', url, data, users)
    assert results == [401, 403, 403, 200]


def test_project_action_stats(client, data):
    public_url = reverse('projects-stats', kwargs={"pk": data.public_project.pk})
    private1_url = reverse('projects-stats', kwargs={"pk": data.private_project1.pk})
    private2_url = reverse('projects-stats', kwargs={"pk": data.private_project2.pk})

    users = [
        None,
        data.registered_user,
        data.project_member_with_perms,
        data.project_owner
    ]
    results = helper_test_http_method(client, 'get', public_url, None, users)
    assert results == [200, 200, 200, 200]
    results = helper_test_http_method(client, 'get', private1_url, None, users)
    assert results == [200, 200, 200, 200]
    results = helper_test_http_method(client, 'get', private2_url, None, users)
    assert results == [404, 404, 200, 200]


def test_project_action_star(client, data):
    public_url = reverse('projects-star', kwargs={"pk": data.public_project.pk})
    private1_url = reverse('projects-star', kwargs={"pk": data.private_project1.pk})
    private2_url = reverse('projects-star', kwargs={"pk": data.private_project2.pk})

    users = [
        None,
        data.registered_user,
        data.project_member_with_perms,
        data.project_owner
    ]
    results = helper_test_http_method(client, 'post', public_url, None, users)
    assert results == [401, 200, 200, 200]
    results = helper_test_http_method(client, 'post', private1_url, None, users)
    assert results == [401, 200, 200, 200]
    results = helper_test_http_method(client, 'post', private2_url, None, users)
    assert results == [404, 404, 200, 200]


def test_project_action_unstar(client, data):
    public_url = reverse('projects-unstar', kwargs={"pk": data.public_project.pk})
    private1_url = reverse('projects-unstar', kwargs={"pk": data.private_project1.pk})
    private2_url = reverse('projects-unstar', kwargs={"pk": data.private_project2.pk})

    users = [
        None,
        data.registered_user,
        data.project_member_with_perms,
        data.project_owner
    ]
    results = helper_test_http_method(client, 'post', public_url, None, users)
    assert results == [401, 200, 200, 200]
    results = helper_test_http_method(client, 'post', private1_url, None, users)
    assert results == [401, 200, 200, 200]
    results = helper_test_http_method(client, 'post', private2_url, None, users)
    assert results == [404, 404, 200, 200]


def test_project_action_issues_stats(client, data):
    public_url = reverse('projects-issues-stats', kwargs={"pk": data.public_project.pk})
    private1_url = reverse('projects-issues-stats', kwargs={"pk": data.private_project1.pk})
    private2_url = reverse('projects-issues-stats', kwargs={"pk": data.private_project2.pk})

    users = [
        None,
        data.registered_user,
        data.project_member_with_perms,
        data.project_owner
    ]
    results = helper_test_http_method(client, 'get', public_url, None, users)
    assert results == [200, 200, 200, 200]
    results = helper_test_http_method(client, 'get', private1_url, None, users)
    assert results == [200, 200, 200, 200]
    results = helper_test_http_method(client, 'get', private2_url, None, users)
    assert results == [404, 404, 200, 200]


def test_project_action_issues_filters_data(client, data):
    public_url = reverse('projects-issue-filters-data', kwargs={"pk": data.public_project.pk})
    private1_url = reverse('projects-issue-filters-data', kwargs={"pk": data.private_project1.pk})
    private2_url = reverse('projects-issue-filters-data', kwargs={"pk": data.private_project2.pk})

    users = [
        None,
        data.registered_user,
        data.project_member_with_perms,
        data.project_owner
    ]
    results = helper_test_http_method(client, 'get', public_url, None, users)
    assert results == [200, 200, 200, 200]
    results = helper_test_http_method(client, 'get', private1_url, None, users)
    assert results == [200, 200, 200, 200]
    results = helper_test_http_method(client, 'get', private2_url, None, users)
    assert results == [404, 404, 200, 200]


def test_project_action_fans(client, data):
    public_url = reverse('projects-fans', kwargs={"pk": data.public_project.pk})
    private1_url = reverse('projects-fans', kwargs={"pk": data.private_project1.pk})
    private2_url = reverse('projects-fans', kwargs={"pk": data.private_project2.pk})

    users = [
        None,
        data.registered_user,
        data.project_member_without_perms,
        data.project_member_with_perms,
        data.project_owner
    ]

    results = helper_test_http_method_and_count(client, 'get', public_url, None, users)
    assert results == [(200, 2), (200, 2), (200, 2), (200, 2), (200, 2)]
    results = helper_test_http_method_and_count(client, 'get', private1_url, None, users)
    assert results == [(200, 2), (200, 2), (200, 2), (200, 2), (200, 2)]
    results = helper_test_http_method_and_count(client, 'get', private2_url, None, users)
    assert results == [(404, 1), (404, 1), (404, 1), (200, 2), (200, 2)]


def test_user_action_starred(client, data):
    url1 = reverse('users-starred', kwargs={"pk": data.project_member_without_perms.pk})
    url2 = reverse('users-starred', kwargs={"pk": data.project_member_with_perms.pk})
    url3 = reverse('users-starred', kwargs={"pk": data.project_owner.pk})

    users = [
        None,
        data.registered_user,
        data.project_member_without_perms,
        data.project_member_with_perms,
        data.project_owner
    ]

    results = helper_test_http_method_and_count(client, 'get', url1, None, users)
    assert results == [(200, 0), (200, 0), (200, 0), (200, 0), (200, 0)]
    results = helper_test_http_method_and_count(client, 'get', url2, None, users)
    assert results == [(200, 3), (200, 3), (200, 3), (200, 3), (200, 3)]
    results = helper_test_http_method_and_count(client, 'get', url3, None, users)
    assert results == [(200, 3), (200, 3), (200, 3), (200, 3), (200, 3)]


def test_project_action_create_template(client, data):
    public_url = reverse('projects-create-template', kwargs={"pk": data.public_project.pk})
    private1_url = reverse('projects-create-template', kwargs={"pk": data.private_project1.pk})
    private2_url = reverse('projects-create-template', kwargs={"pk": data.private_project2.pk})

    users = [
        None,
        data.registered_user,
        data.project_member_without_perms,
        data.project_member_with_perms,
        data.project_owner,
        data.superuser,
    ]

    template_data = json.dumps({
        "template_name": "test",
        "template_description": "test",
    })

    results = helper_test_http_method(client, 'post', public_url, template_data, users)
    assert results == [401, 403, 403, 403, 403, 201]
    results = helper_test_http_method(client, 'post', private1_url, template_data, users)
    assert results == [401, 403, 403, 403, 403, 201]
    results = helper_test_http_method(client, 'post', private2_url, template_data, users)
    assert results == [404, 404, 404, 403, 403, 201]


def test_invitations_list(client, data):
    url = reverse('invitations-list')

    users = [
        None,
        data.registered_user,
        data.project_member_with_perms,
        data.project_owner
    ]
    results = helper_test_http_method(client, 'get', url, None, users)
    assert results == [403, 403, 403, 403]


def test_invitations_retrieve(client, data):
    invitation = f.MembershipFactory(user=None)

    url = reverse('invitations-detail', kwargs={'token': invitation.token})

    users = [
        None,
        data.registered_user,
        data.project_member_with_perms,
        data.project_owner
    ]
    results = helper_test_http_method(client, 'get', url, None, users)
    assert results == [200, 200, 200, 200]
