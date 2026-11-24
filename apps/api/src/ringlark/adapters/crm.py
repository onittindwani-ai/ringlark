"""Twenty CRM over GraphQL (tier A, tested against a mock). Field names are UNVERIFIED against a real workspace."""

from __future__ import annotations

import httpx

from ringlark.adapters.base import PersonRecord, safe_base_url
from sendora_core.adapters import AdapterError
from sendora_core.safety import write_action

FIND_BY_PHONE = "query FindByPhone($phone: String!) { people(filter: {phones: {primaryPhoneNumber: {eq: $phone}}}) { edges { node { id name { firstName lastName } jobTitle city } } } }"
CREATE_PERSON = "mutation CreatePerson($data: PersonCreateInput!) { createPerson(data: $data) { id } }"
CREATE_NOTE = "mutation CreateNote($data: NoteCreateInput!) { createNote(data: $data) { id } }"


class TwentyCrm:
    def __init__(self, settings, client: httpx.Client | None = None):
        self.settings = settings
        if client is not None:
            self.client = client
        else:
            if not settings.twenty_base_url or not settings.twenty_api_key:
                raise AdapterError("TWENTY_BASE_URL and TWENTY_API_KEY must both be set.")
            self.client = httpx.Client(base_url=safe_base_url(settings.twenty_base_url), timeout=15, headers={"Authorization": f"Bearer {settings.twenty_api_key}"})

    def _gql(self, op: str, query: str, variables: dict) -> dict:
        r = self.client.post("/graphql", json={"operationName": op, "query": query, "variables": variables})
        if r.status_code == 401:
            raise AdapterError("Twenty rejected the API key.")
        body = r.json()
        if body.get("errors"):
            raise AdapterError(f"Twenty said: {body['errors'][0].get('message', 'unknown error')}")
        return body["data"]

    def find_by_phone(self, phone: str) -> PersonRecord | None:
        edges = self._gql("FindByPhone", FIND_BY_PHONE, {"phone": phone})["people"]["edges"]
        if not edges:
            return None
        n = edges[0]["node"]
        return PersonRecord(first_name=n["name"]["firstName"], last_name=n["name"]["lastName"], title=n.get("jobTitle") or "", phone=phone, extra={"id": n["id"]})

    @write_action("crm.upsert")
    def upsert_person(self, person: PersonRecord) -> str:
        found = self.find_by_phone(person.phone) if person.phone else None
        if found:
            pid = str(found.extra["id"])
        else:
            data = {"name": {"firstName": person.first_name, "lastName": person.last_name}, "phones": {"primaryPhoneNumber": person.phone}, "jobTitle": person.title}
            pid = str(self._gql("CreatePerson", CREATE_PERSON, {"data": data})["createPerson"]["id"])
        note = person.extra.get("note")
        if note:
            self._gql("CreateNote", CREATE_NOTE, {"data": {"title": "Call summary", "bodyV2": {"markdown": note}, "personId": pid}})
        return pid

    def healthcheck(self) -> tuple[bool, str]:
        try:
            self._gql("FindByPhone", FIND_BY_PHONE, {"phone": "+14155550180"})
            return True, "Twenty answered and accepted the key."
        except AdapterError as exc:
            return False, str(exc)
        except httpx.HTTPError as exc:
            return False, f"Could not reach Twenty: {type(exc).__name__}."
