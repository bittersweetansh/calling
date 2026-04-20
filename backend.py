from fastapi import FastAPI, HTTPException, Depends
from sqlalchemy.orm import Session
from sqlalchemy import select, func
from datetime import datetime, timedelta
import re

from database import init_db, Appointment, get_db

app = FastAPI()
init_db()

# =========================
# SMART PARSER (STRONG + FLEXIBLE)
# =========================
def parse_datetime(text: str):
    text = (text or "").lower().strip()
    now = datetime.now()

    # -------- HUMAN LANGUAGE HANDLING --------
    if "evening" in text:
        text += " 6pm"
    if "morning" in text:
        text += " 10am"
    if "afternoon" in text:
        text += " 2pm"
    if "night" in text:
        text += " 9pm"

    # -------- DATE --------
    if "tomorrow" in text:
        target_date = now.date() + timedelta(days=1)
    elif "day after tomorrow" in text:
        target_date = now.date() + timedelta(days=2)
    else:
        target_date = now.date()

    # -------- CLEAN --------
    cleaned = text.replace(" ", "")

    # -------- TIME --------
    match = re.search(r"(\d{1,2})(?::(\d{2}))?(am|pm)", cleaned)

    if not match:
        # fallback safe slot (next hour rounded)
        fallback = (now + timedelta(hours=1)).replace(minute=0, second=0, microsecond=0)
        print("⚠️ Fallback used for:", text, "→", fallback)
        return fallback

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
    print("🔥 SCHEDULE REQ:", req)

    name = req.get("name", "").strip()
    address = req.get("address", "").strip()
    natural_time = req.get("natural_time", "")

    if not name or not natural_time:
        raise HTTPException(400, "Missing required fields")

    dt_value = parse_datetime(natural_time)

    if not is_available(db, dt_value):
        raise HTTPException(400, "Slot already booked")

    appt = Appointment(
        name=name,
        address=address,
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
    print("🔁 RESCHEDULE REQ:", req)

    name = req.get("name", "").strip()
    old_time = req.get("old_time", "")
    new_time = req.get("new_time", "")

    if not name or not old_time or not new_time:
        raise HTTPException(400, "Missing required fields")

    old_dt = parse_datetime(old_time)
    new_dt = parse_datetime(new_time)

    start = old_dt - timedelta(minutes=3)
    end = old_dt + timedelta(minutes=3)

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

    if not is_available(db, new_dt):
        raise HTTPException(400, "New slot already booked")

    appt.date_time = new_dt
    db.commit()

    return {
        "status": "rescheduled",
        "name": appt.name,
        "new_time": str(new_dt)
    }


@app.get("/availability")
def availability(date: str, db: Session = Depends(get_db)):
    print("📊 AVAILABILITY REQ:", date)

    base = parse_datetime(date)

    slots = []
    for hour in range(9, 21):  # 9AM → 9PM
        slot = base.replace(hour=hour, minute=0, second=0, microsecond=0)

        if is_available(db, slot):
            slots.append(str(slot))

    return {"available_slots": slots}


@app.get("/appointments")
def get_all(db: Session = Depends(get_db)):
    result = db.execute(select(Appointment))
    return result.scalars().all()


# =========================
# OPTIONAL: CLEAR DB (FOR TESTING)
# =========================
@app.delete("/clear-db")
def clear_db(db: Session = Depends(get_db)):
    db.query(Appointment).delete()
    db.commit()
    return {"status": "database cleared"}
