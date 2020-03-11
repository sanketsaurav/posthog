from posthog.models import Event, Person
from rest_framework import serializers, viewsets, response
from rest_framework.decorators import action
from django.db.models import Prefetch, QuerySet
from typing import Union
from .base import CursorPagination

class PersonSerializer(serializers.HyperlinkedModelSerializer):
    last_event = serializers.SerializerMethodField()
    name = serializers.SerializerMethodField()

    class Meta:
        model = Person
        fields = ['id', 'name', 'distinct_ids', 'properties', 'last_event', 'created_at']

    def get_last_event(self, person: Person) -> Union[dict, None]:
        if not self.context['request'].GET.get('include_last_event'):
            return None
        last_event = Event.objects.filter(team_id=person.team_id, distinct_id__in=person.distinct_ids).order_by('-timestamp').first()
        if last_event:
            return {'timestamp': last_event.timestamp}
        else:
            return None

    def get_name(self, person: Person) -> str:
        if person.properties.get('email'):
            return person.properties['email']
        if len(person.distinct_ids) > 0:
            return person.distinct_ids[-1]
        return person.pk

class PersonViewSet(viewsets.ModelViewSet):
    queryset = Person.objects.all()
    serializer_class = PersonSerializer
    pagination_class = CursorPagination

    def _filter_request(self, request: request.Request, queryset: QuerySet) -> QuerySet:
        if request.GET.get('id'):
            people = request.GET['id'].split(',')
            queryset = queryset.filter(id__in=people)
        if request.GET.get('search'):
            parts = request.GET['search'].split(' ')
            contains = []
            for part in parts:
                if ':' in part:
                    queryset = queryset.filter(properties__has_key=part.split(':')[1])
                else:
                    contains.append(part)
            queryset = queryset.filter(properties__icontains=' '.join(contains))

        queryset = queryset.prefetch_related(Prefetch('persondistinctid_set', to_attr='distinct_ids_cache'))
        return queryset

    def get_queryset(self):
        queryset = super().get_queryset()
        team = self.request.user.team_set.get()
        queryset = queryset.filter(team=team)
        queryset = self._filter_request(self.request, queryset)
        return queryset.order_by('-id')

    @action(methods=['GET'], detail=False)
    def by_distinct_id(self, request):
        person = self.get_queryset().get(persondistinctid__distinct_id=str(request.GET['distinct_id']))
        return response.Response(PersonSerializer(person, context={'request': request}).data)