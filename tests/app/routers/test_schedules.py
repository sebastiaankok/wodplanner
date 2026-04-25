"""Tests for app/routers/schedules.py."""

from datetime import date

from wodplanner.models.schedule import Schedule


class TestSchedulesRouter:
    def test_get_by_date_empty(self, app_client):
        response = app_client.get("/api/schedules/2026-04-25")
        assert response.status_code == 200
        assert response.json() == []

    def test_get_by_date_populated(self, app_client, schedule_service):
        schedule_service.add(
            Schedule(
                date=date(2026, 4, 25),
                class_type="CrossFit",
                warmup_mobility="warm",
                strength_specialty="back squat",
                metcon="21-15-9",
                gym_id=100,
            )
        )
        response = app_client.get("/api/schedules/2026-04-25")
        assert response.status_code == 200
        body = response.json()
        assert len(body) == 1
        assert body[0]["class_type"] == "CrossFit"
        assert body[0]["metcon"] == "21-15-9"

    def test_get_by_date_and_class_200(self, app_client, schedule_service):
        schedule_service.add(
            Schedule(
                date=date(2026, 4, 25),
                class_type="CrossFit",
                metcon="m",
                gym_id=100,
            )
        )
        response = app_client.get("/api/schedules/2026-04-25/CrossFit")
        assert response.status_code == 200
        assert response.json()["class_type"] == "CrossFit"

    def test_get_by_date_and_class_404(self, app_client):
        response = app_client.get("/api/schedules/2026-04-25/Nonexistent")
        assert response.status_code == 404
