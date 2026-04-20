from fastapi import FastAPI, HTTPException, Depends
from sqlalchemy.orm import Session
from sqlalchemy import select, func
from datetime import datetime, timedelta
import re

from database import init_db, Appointment, get_db

# =========================
# INIT
# =========================
app = FastAPI()
init_db()


# =========================
# PARSER (ROBUST VERSION)
# =========================
def parse_datetime(text: str):
    text = (text or "").lower().strip()
    now = datetime.now()

    # -------- DATE --------
    if "tomorrow" in text:
        target_date = now.date() + timedelta(days=1)
    else:
        target_date = now.date()

    # -------- CLEAN TEXT --------
    cleaned = text.replace(" ", "")

    # -------- TIME --------
    match = re.search(r"(\d{1,2})(?::(\d{2}))?(am|pm)", cleaned)

    if not match:
        print("⚠️ Fallback time used for:", text)
        return (now + timedelta(hours=1)).replace(minute=0, second=0, microsecond=0)

    hour = int(match.group(1))
    minute = int(match.group(2) or 0)
    ampm = match.group(3)

    if ampm == "pm" and hour != 12:
        hour += 12
    if ampm == "am" and hour == 12:
        hour = 0

    return datetime(
        year=target_date.year,
        month=target_date.month,
        day=target_date.day,
        hour=hour,
        minute=minute,
        second=0,
        microsecond=0
    )


# =========================
# AVAILABILITY CHECK
# =========================
def is_available(db, dt_value):
    existing = db.execute(
        select(Appointment).where(
            Appointment.date_time == dt_value,
            Appointment.canceled == False
        )
    ).scalars().first()

    return existing is None


# =========================
# ROUTES
# =========================
@app.get("/")
def root():
    return {"status": "API is running"}


@app.post("/schedule")
def schedule(req: dict, db: Session = Depends(get_db)):
    print("REQ RECEIVED:", req)

    dt_value = parse_datetime(req.get("natural_time", ""))

    # prevent duplicate slot booking
    existing = db.execute(
        select(Appointment).where(
            Appointment.date_time == dt_value,
            Appointment.canceled == False
        )
    ).scalars().first()

    if existing:
        raise HTTPException(400, "Slot already booked")

    appt = Appointment(
        name=req.get("name", "").strip(),
        address=req.get("address", "").strip(),
        date_time=dt_value
    )

    db.add(appt)
    db.commit()
    db.refresh(appt)

    return {
        "status": "booked",
        "id": appt.id,
        "name": appt.name,
        "time": str(appt.date_time)
    }


@app.post("/reschedule")
def reschedule(req: dict, db: Session = Depends(get_db)):
    print("REQ RECEIVED:", req)

    old_dt = parse_datetime(req.get("old_time", ""))
    new_dt = parse_datetime(req.get("new_time", ""))

    name = req.get("name", "").strip()

    # time window ±2 min
    start = old_dt - timedelta(minutes=2)
    end = old_dt + timedelta(minutes=2)

    appt = db.execute(
        select(Appointment).where(
            func.lower(Appointment.name) == name.lower(),
            Appointment.date_time >= start,
            Appointment.date_time <= end,
            Appointment.canceled == False
        )
    ).scalars().first()

    if not appt:
        raise HTTPException(404, "Appointment not found")

    # check new slot
    existing = db.execute(
        select(Appointment).where(
            Appointment.date_time == new_dt,
            Appointment.canceled == False
        )
    ).scalars().first()

    if existing:
        raise HTTPException(400, "New slot already booked")

    appt.date_time = new_dt
    db.commit()

    return {
        "status": "rescheduled",
        "name": appt.name,
        "new_time": str(new_dt)
    }


@app.get("/appointments")
def get_all(db: Session = Depends(get_db)):
    result = db.execute(select(Appointment))
    return result.scalars().all()


@app.get("/availability")
def availability(date: str, db: Session = Depends(get_db)):
    from datetime import datetime, timedelta

    base = parse_datetime(date)

    slots = []
    for i in range(9, 18):  # 9am to 6pm
        slot = base.replace(hour=i, minute=0)

        exists = db.execute(
            select(Appointment).where(
                Appointment.date_time == slot,
                Appointment.canceled == False
            )
        ).scalars().first()

        if not exists:
            slots.append(str(slot))

    return {"available_slots": slots}