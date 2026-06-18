-- 012_wheel_assignment.sql
-- Track assignment price on WheelSC positions so the dashboard can flag
-- "WHEEL-STUCK" (stock still below assignment cost after being assigned).
-- Populated by Routine A when a new WheelSC is detected.

ALTER TABLE positions ADD COLUMN assignment_price NUMERIC(14,2);

-- Expand the flag_type constraint to include wheel-specific risk flags.
ALTER TABLE daily_flags DROP CONSTRAINT flag_type_check;
ALTER TABLE daily_flags ADD CONSTRAINT flag_type_check CHECK (
    flag_type IN (
        'HARVEST', 'UNDERWATER', 'TRIM', 'THESIS-CHECK',
        'EXPIRES', 'NEW', 'OTHER',
        'WHEEL-AT-RISK',   -- WheelSP within 5% of strike / ITM
        'WHEEL-STUCK'      -- assigned shares still below assignment price
    )
);
