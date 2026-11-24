"""Fake Twenty CRM GraphQL endpoint. It answers the operations Ringlark sends, by operationName.

The exact field names of a real Twenty workspace are UNVERIFIED (docs did not show the schema, and an API key can see a
different schema than a session). The mock only proves the adapter builds requests and reads replies consistently.
"""

from __future__ import annotations

import uuid

from fastapi import FastAPI, Header, Request
from fastapi.responses import JSONResponse


class TwentyMock:
    def __init__(self, api_key: str = "mock-twenty-key"):
        self.api_key = api_key
        self.people: dict[str, dict] = {}
        self.companies: dict[str, dict] = {}
        self.notes: list[dict] = []
        self.app = self._build()

    def _build(self) -> FastAPI:
        app = FastAPI(title="Twenty mock")

        @app.post("/graphql")
        async def graphql(request: Request, authorization: str | None = Header(default=None)):
            if authorization != f"Bearer {self.api_key}":
                return JSONResponse({"errors": [{"message": "Unauthorized"}]}, 401)
            body = await request.json()
            op, v = body.get("operationName"), body.get("variables") or {}
            if op == "CreateCompany":
                cid = str(uuid.uuid4())
                self.companies[cid] = {"id": cid, **v["data"]}
                return {"data": {"createCompany": {"id": cid}}}
            if op == "CreatePerson":
                phone = (v["data"].get("phones") or {}).get("primaryPhoneNumber")
                if phone and any((p.get("phones") or {}).get("primaryPhoneNumber") == phone for p in self.people.values()):
                    return {"errors": [{"message": "Duplicate entry"}]}
                pid = str(uuid.uuid4())
                self.people[pid] = {"id": pid, **v["data"]}
                return {"data": {"createPerson": {"id": pid}}}
            if op == "FindByPhone":
                hits = [p for p in self.people.values() if (p.get("phones") or {}).get("primaryPhoneNumber") == v["phone"]]
                return {"data": {"people": {"edges": [{"node": {"id": p["id"], "name": p.get("name", {"firstName": "", "lastName": ""}), "jobTitle": p.get("jobTitle", ""), "city": ""}} for p in hits]}}}
            if op == "CreateNote":
                self.notes.append(v["data"])
                return {"data": {"createNote": {"id": str(uuid.uuid4())}}}
            if op == "FindPeople":
                hits = []
                return {"data": {"people": {"edges": [{"node": p} for p in hits]}}}
            return JSONResponse({"errors": [{"message": f"Unknown operation {op}"}]}, 400)

        return app
