from sqlalchemy import text

from src.data.clients.postgres_client import AsyncSessionLocal


async def seed_available_slots():
    async with AsyncSessionLocal() as session:
        await session.execute(
            text("""
    INSERT INTO available_slots
    (provider_id, availability_date, start_time, end_time, notes)
    VALUES
    -- Dr. Arjun Kumar (provider_id=1) | Mar 16-22
    (1, '2026-03-16', '09:00', '09:30', 'Morning slot'),
    (1, '2026-03-16', '09:30', '10:00', 'Morning slot'),
    (1, '2026-03-16', '10:00', '10:30', 'Morning slot'),
    (1, '2026-03-16', '10:30', '11:00', 'Morning slot'),
    (1, '2026-03-16', '14:00', '14:30', 'Afternoon slot'),
    (1, '2026-03-16', '14:30', '15:00', 'Afternoon slot'),
    (1, '2026-03-17', '09:00', '09:30', 'Morning slot'),
    (1, '2026-03-17', '09:30', '10:00', 'Morning slot'),
    (1, '2026-03-17', '10:00', '10:30', 'Morning slot'),
    (1, '2026-03-17', '14:00', '14:30', 'Afternoon slot'),
    (1, '2026-03-17', '14:30', '15:00', 'Afternoon slot'),
    (1, '2026-03-17', '15:00', '15:30', 'Afternoon slot'),
    (1, '2026-03-18', '09:00', '09:30', 'Morning slot'),
    (1, '2026-03-18', '09:30', '10:00', 'Morning slot'),
    (1, '2026-03-18', '10:00', '10:30', 'Morning slot'),
    (1, '2026-03-18', '10:30', '11:00', 'Morning slot'),
    (1, '2026-03-18', '14:00', '14:30', 'Afternoon slot'),
    (1, '2026-03-18', '14:30', '15:00', 'Afternoon slot'),
    (1, '2026-03-19', '09:00', '09:30', 'Morning slot'),
    (1, '2026-03-19', '09:30', '10:00', 'Morning slot'),
    (1, '2026-03-19', '10:00', '10:30', 'Morning slot'),
    (1, '2026-03-19', '14:00', '14:30', 'Afternoon slot'),
    (1, '2026-03-20', '09:00', '09:30', 'Morning slot'),
    (1, '2026-03-20', '09:30', '10:00', 'Morning slot'),
    (1, '2026-03-20', '10:00', '10:30', 'Morning slot'),
    (1, '2026-03-20', '10:30', '11:00', 'Morning slot'),
    (1, '2026-03-20', '14:00', '14:30', 'Afternoon slot'),
    (1, '2026-03-20', '14:30', '15:00', 'Afternoon slot'),
    (1, '2026-03-21', '09:00', '09:30', 'Morning slot'),
    (1, '2026-03-21', '09:30', '10:00', 'Morning slot'),
    (1, '2026-03-21', '10:00', '10:30', 'Morning slot'),
    (1, '2026-03-21', '14:00', '14:30', 'Afternoon slot'),
    (1, '2026-03-21', '14:30', '15:00', 'Afternoon slot'),

    -- Dr. Meena Ravi (provider_id=2) | Mar 16-22
    (2, '2026-03-16', '10:00', '10:30', 'Heart checkup'),
    (2, '2026-03-16', '10:30', '11:00', 'Heart checkup'),
    (2, '2026-03-16', '11:00', '11:30', 'Heart checkup'),
    (2, '2026-03-16', '16:00', '16:30', 'Evening slot'),
    (2, '2026-03-16', '16:30', '17:00', 'Evening slot'),
    (2, '2026-03-17', '10:00', '10:30', 'Heart checkup'),
    (2, '2026-03-17', '10:30', '11:00', 'Heart checkup'),
    (2, '2026-03-17', '16:00', '16:30', 'Evening slot'),
    (2, '2026-03-17', '16:30', '17:00', 'Evening slot'),
    (2, '2026-03-17', '17:00', '17:30', 'Evening slot'),
    (2, '2026-03-18', '10:00', '10:30', 'Heart checkup'),
    (2, '2026-03-18', '10:30', '11:00', 'Heart checkup'),
    (2, '2026-03-18', '11:00', '11:30', 'Heart checkup'),
    (2, '2026-03-18', '11:30', '12:00', 'Heart checkup'),
    (2, '2026-03-18', '16:00', '16:30', 'Evening slot'),
    (2, '2026-03-18', '16:30', '17:00', 'Evening slot'),
    (2, '2026-03-19', '10:00', '10:30', 'Heart checkup'),
    (2, '2026-03-19', '10:30', '11:00', 'Heart checkup'),
    (2, '2026-03-19', '16:00', '16:30', 'Evening slot'),
    (2, '2026-03-19', '16:30', '17:00', 'Evening slot'),
    (2, '2026-03-20', '10:00', '10:30', 'Heart checkup'),
    (2, '2026-03-20', '10:30', '11:00', 'Heart checkup'),
    (2, '2026-03-20', '11:00', '11:30', 'Heart checkup'),
    (2, '2026-03-20', '16:00', '16:30', 'Evening slot'),
    (2, '2026-03-20', '16:30', '17:00', 'Evening slot'),
    (2, '2026-03-21', '10:00', '10:30', 'Heart checkup'),
    (2, '2026-03-21', '10:30', '11:00', 'Heart checkup'),
    (2, '2026-03-21', '11:00', '11:30', 'Heart checkup'),
    (2, '2026-03-21', '16:00', '16:30', 'Evening slot'),
    (2, '2026-03-21', '16:30', '17:00', 'Evening slot'),

    -- Dr. Rahul Sharma (provider_id=3) | Mar 16-22
    (3, '2026-03-16', '09:00', '09:30', 'Kids clinic'),
    (3, '2026-03-16', '09:30', '10:00', 'Kids clinic'),
    (3, '2026-03-16', '10:00', '10:30', 'Kids clinic'),
    (3, '2026-03-16', '11:00', '11:30', 'Kids checkup'),
    (3, '2026-03-16', '15:00', '15:30', 'Vaccination slot'),
    (3, '2026-03-16', '15:30', '16:00', 'Vaccination slot'),
    (3, '2026-03-17', '09:00', '09:30', 'Kids clinic'),
    (3, '2026-03-17', '09:30', '10:00', 'Kids clinic'),
    (3, '2026-03-17', '11:00', '11:30', 'Kids checkup'),
    (3, '2026-03-17', '11:30', '12:00', 'Kids checkup'),
    (3, '2026-03-17', '15:00', '15:30', 'Vaccination slot'),
    (3, '2026-03-17', '15:30', '16:00', 'Vaccination slot'),
    (3, '2026-03-17', '16:00', '16:30', 'Vaccination slot'),
    (3, '2026-03-18', '09:00', '09:30', 'Kids clinic'),
    (3, '2026-03-18', '09:30', '10:00', 'Kids clinic'),
    (3, '2026-03-18', '10:00', '10:30', 'Kids clinic'),
    (3, '2026-03-18', '11:00', '11:30', 'Kids checkup'),
    (3, '2026-03-18', '11:30', '12:00', 'Kids checkup'),
    (3, '2026-03-18', '15:00', '15:30', 'Vaccination slot'),
    (3, '2026-03-18', '15:30', '16:00', 'Vaccination slot'),
    (3, '2026-03-19', '09:00', '09:30', 'Kids clinic'),
    (3, '2026-03-19', '09:30', '10:00', 'Kids clinic'),
    (3, '2026-03-19', '11:00', '11:30', 'Kids checkup'),
    (3, '2026-03-19', '15:00', '15:30', 'Vaccination slot'),
    (3, '2026-03-19', '15:30', '16:00', 'Vaccination slot'),
    (3, '2026-03-20', '09:00', '09:30', 'Kids clinic'),
    (3, '2026-03-20', '09:30', '10:00', 'Kids clinic'),
    (3, '2026-03-20', '10:00', '10:30', 'Kids clinic'),
    (3, '2026-03-20', '11:00', '11:30', 'Kids checkup'),
    (3, '2026-03-20', '11:30', '12:00', 'Kids checkup'),
    (3, '2026-03-20', '15:00', '15:30', 'Vaccination slot'),
    (3, '2026-03-21', '09:00', '09:30', 'Kids clinic'),
    (3, '2026-03-21', '09:30', '10:00', 'Kids clinic'),
    (3, '2026-03-21', '11:00', '11:30', 'Kids checkup'),
    (3, '2026-03-21', '11:30', '12:00', 'Kids checkup'),
    (3, '2026-03-21', '15:00', '15:30', 'Vaccination slot'),
    (3, '2026-03-21', '15:30', '16:00', 'Vaccination slot')

    ON CONFLICT (provider_id, availability_date, start_time, end_time) DO NOTHING;
    """)
        )
        await session.commit()


# await session.execute(
# text("""
# INSERT INTO available_slots
# (provider_id, availability_date, start_time, end_time, notes)

# SELECT
#     d.provider_id,
#     day::date AS availability_date,
#     time_slot AS start_time,
#     time_slot + interval '30 minutes' AS end_time,
#     'Auto slot' AS notes
# FROM
#     generate_series('2026-03-13'::date, '2026-03-20'::date, interval '1 day') AS day
# CROSS JOIN
#     (VALUES (1),(2),(3)) AS d(provider_id)
# CROSS JOIN
#     generate_series('09:00'::time, '18:30'::time, interval '30 minutes') AS time_slot
# LIMIT 480

# ON CONFLICT (provider_id, availability_date, start_time, end_time) DO NOTHING;
# """)
# )
