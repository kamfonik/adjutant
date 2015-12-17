# Copyright (C) 2015 Catalyst IT Ltd
#
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.

from django.utils import timezone
from django.conf import settings
from rest_framework.response import Response

from stacktask.api.v1 import tasks
from stacktask.api import utils
from stacktask.api import models
from stacktask.actions import user_store


class UserList(tasks.InviteUser):

    @utils.mod_or_owner
    def get(self, request):
        """Get a list of all users who have been added to a project"""
        class_conf = settings.TASK_SETTINGS.get('edit_user', {})
        role_blacklist = class_conf.get('role_blacklist', [])
        user_list = []
        id_manager = user_store.IdentityManager()
        project_id = request.keystone_user['project_id']
        project = id_manager.get_project(project_id)

        active_emails = set()
        for user in project.list_users():
            skip = False
            self.logger.info(user)
            roles = []
            for role in id_manager.get_roles(user, project):
                if role.name in role_blacklist:
                    skip = True
                    continue
                roles.append(role.name)
            if skip:
                continue

            email = getattr(user, 'email', '')
            active_emails.add(email)
            user_list.append({'id': user.id,
                              'name': user.username,
                              'email': email,
                              'roles': roles,
                              'status': 'Active'
                              })

        # Get my active tasks for this project:
        project_tasks = models.Task.objects.filter(
            project_id=project_id,
            task_type="invite_user",
            completed=0,
            cancelled=0)

        registrations = []
        for task in project_tasks:
            status = "Unconfirmed"
            for token in task.tokens:
                if token.expired:
                    status = "Expired"

            for notification in task.notifications:
                if notification.error:
                    status = "Failed"

            task_data = {}
            for action in task.actions:
                task_data.update(action.action_data)

            registrations.append(
                {'uuid': task.uuid, 'task_data': task_data, 'status': status})

        for task in registrations:
            if task['task_data']['email'] not in active_emails:
                user_list.append({'id': task['uuid'],
                                  'name': task['task_data']['email'],
                                  'email': task['task_data']['email'],
                                  'roles': task['task_data']['roles'],
                                  'status': task['status']})

        return Response({'users': user_list})


class UserDetail(tasks.TaskView):
    task_type = 'edit_user'

    @utils.mod_or_owner
    def get(self, request, user_id):
        """
        Get user info based on the user id.

        Will only find users in your project.
        """
        id_manager = user_store.IdentityManager()
        user = id_manager.get_user(user_id)

        no_user = {'errors': ['No user with this id.']}
        if not user:
            return Response(no_user, status=404)

        class_conf = settings.TASK_SETTINGS.get(self.task_type, {})
        role_blacklist = class_conf.get('role_blacklist', [])
        project_id = request.keystone_user['project_id']
        project = id_manager.get_project(project_id)

        roles = [role.name for role in id_manager.get_roles(user, project)]
        roles_blacklisted = set(role_blacklist) & set(roles)

        if not roles or roles_blacklisted:
            return Response(no_user, status=404)
        return Response({'id': user.id,
                         "username": user.username,
                         "email": getattr(user, 'email', ''),
                         'roles': roles})

    @utils.mod_or_owner
    def delete(self, request, user_id):
        """
        Remove this user from the project.
        This may cancel a pending user invite, or simply revoke roles.
        """
        id_manager = user_store.IdentityManager()
        user = id_manager.get_user(user_id)
        project_id = request.keystone_user['project_id']
        # NOTE(dale): For now, we only support cancelling pending invites.
        if user:
            return Response(
                {'errors': [
                    'Revoking keystone users not implemented. ' +
                    'Try removing all roles instead.']},
                status=501)
        project_tasks = models.Task.objects.filter(
            project_id=project_id,
            task_type="invite_user",
            completed=0,
            cancelled=0)
        for task in project_tasks:
            if task.uuid == user_id:
                task.add_action_note(self.__class__.__name__, 'Cancelled.')
                task.cancelled = True
                task.save()
                return Response('Cancelled pending invite task!', status=200)
        return Response('Not found.', status=404)


class UserRoles(tasks.TaskView):

    default_action = 'EditUserRoles'
    task_type = 'edit_roles'

    @utils.mod_or_owner
    def get(self, request, user_id):
        """
        Get user info based on the user id.
        """
        id_manager = user_store.IdentityManager()
        user = id_manager.get_user(user_id)
        project_id = request.keystone_user['project_id']
        project = id_manager.get_project(project_id)
        roles = []
        for role in id_manager.get_roles(user, project):
            roles.append(role.to_dict())
        return Response({"roles": roles})

    @utils.mod_or_owner
    def put(self, request, user_id, format=None):
        """
        Add user roles to the current project.
        """
        request.data['remove'] = False
        if 'project_id' not in request.data:
            request.data['project_id'] = request.keystone_user['project_id']
        request.data['user_id'] = user_id

        self.logger.info("(%s) - New EditUserRoles request." % timezone.now())
        processed = self.process_actions(request)

        errors = processed.get('errors', None)
        if errors:
            self.logger.info("(%s) - Validation errors with registration." %
                             timezone.now())
            return Response(errors, status=400)

        task = processed['task']
        self.logger.info("(%s) - AutoApproving EditUserRoles request."
                         % timezone.now())
        return self.approve(task)

    @utils.mod_or_owner
    def delete(self, request, user_id, format=None):
        """
        Revoke user roles to the current project.
        This only supports Active users.
        """
        request.data['remove'] = True
        if 'project_id' not in request.data:
            request.data['project_id'] = request.keystone_user['project_id']
        request.data['user_id'] = user_id

        self.logger.info("(%s) - New EditUser request." % timezone.now())
        processed = self.process_actions(request)

        errors = processed.get('errors', None)
        if errors:
            self.logger.info("(%s) - Validation errors with registration." %
                             timezone.now())
            return Response(errors, status=400)

        task = processed['task']
        self.logger.info("(%s) - AutoApproving EditUser request."
                         % timezone.now())
        return self.approve(task)


class RoleList(tasks.TaskView):
    task_type = 'edit_roles'

    @utils.mod_or_owner
    def get(self, request):
        """Returns a list of roles that may be managed for this project"""

        # get roles for this user on the project
        user_roles = request.keystone_user['roles']
        managable_role_names = user_store.get_managable_roles(user_roles)

        id_manager = user_store.IdentityManager()

        # look up role names and form output dict of valid roles
        managable_roles = []
        for role_name in managable_role_names:
            role = id_manager.find_role(role_name)
            if role:
                managable_roles.append(role.to_dict())

        return Response({'roles': managable_roles})


class UserResetPassword(tasks.ResetPassword):
    """
    The openstack forgot password endpoint.
    ---
    """

    def get(self, request):
        """
        The ResetPassword endpoint does not support GET.
        This returns a 404.
        """
        return Response(status=404)


class UserSetPassword(tasks.ResetPassword):
    """
    The openstack endpoint to force a password reset.
    ---
    """

    task_type = "force_password"

    def get(self, request):
        """
        The ForcePassword endpoint does not support GET.
        This returns a 404.
        """
        return Response(status=404)

    @utils.admin
    def post(self, request, format=None):
        return super(UserSetPassword, self).post(request)
