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

from rest_framework import serializers


class NewDefaultNetworkSerializer(serializers.Serializer):
    setup_network = serializers.BooleanField(default=True)
    project_id = serializers.CharField(max_length=64)
    region = serializers.CharField(max_length=100)


class NewProjectDefaultNetworkSerializer(serializers.Serializer):
    setup_network = serializers.BooleanField(default=False)
    region = serializers.CharField(max_length=100)


class AddDefaultUsersToProjectSerializer(serializers.Serializer):
    domain_id = serializers.CharField(max_length=64, default='default')
