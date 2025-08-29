# Database Initialization Script for Elderly Care AI System

-- Create database and user
CREATE DATABASE IF NOT EXISTS elderly_care_db;
CREATE USER IF NOT EXISTS elderly_care WITH PASSWORD 'password123';
GRANT ALL PRIVILEGES ON DATABASE elderly_care_db TO elderly_care;

-- Connect to the database
\c elderly_care_db;

-- Grant schema permissions
GRANT ALL ON SCHEMA public TO elderly_care;
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO elderly_care;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO elderly_care;

-- Create extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pg_trgm"; -- For text search

-- Create indexes for better performance
CREATE INDEX IF NOT EXISTS idx_users_device_id ON users(device_id);
CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);
CREATE INDEX IF NOT EXISTS idx_users_role ON users(role);

CREATE INDEX IF NOT EXISTS idx_health_records_user_id ON health_records(user_id);
CREATE INDEX IF NOT EXISTS idx_health_records_timestamp ON health_records(timestamp);
CREATE INDEX IF NOT EXISTS idx_health_records_overall_alert ON health_records(overall_health_alert);

CREATE INDEX IF NOT EXISTS idx_safety_records_user_id ON safety_records(user_id);
CREATE INDEX IF NOT EXISTS idx_safety_records_timestamp ON safety_records(timestamp);
CREATE INDEX IF NOT EXISTS idx_safety_records_fall_detected ON safety_records(fall_detected);

CREATE INDEX IF NOT EXISTS idx_reminders_user_id ON reminders(user_id);
CREATE INDEX IF NOT EXISTS idx_reminders_scheduled_time ON reminders(scheduled_time);
CREATE INDEX IF NOT EXISTS idx_reminders_type ON reminders(reminder_type);

CREATE INDEX IF NOT EXISTS idx_alerts_user_id ON alerts(user_id);
CREATE INDEX IF NOT EXISTS idx_alerts_created_at ON alerts(created_at);
CREATE INDEX IF NOT EXISTS idx_alerts_priority ON alerts(priority);
CREATE INDEX IF NOT EXISTS idx_alerts_resolved ON alerts(is_resolved);

-- Create composite indexes for common queries
CREATE INDEX IF NOT EXISTS idx_health_user_timestamp ON health_records(user_id, timestamp);
CREATE INDEX IF NOT EXISTS idx_safety_user_timestamp ON safety_records(user_id, timestamp);
CREATE INDEX IF NOT EXISTS idx_reminders_user_scheduled ON reminders(user_id, scheduled_time);

-- Create partial indexes for active records
CREATE INDEX IF NOT EXISTS idx_active_users ON users(id) WHERE is_active = true;
CREATE INDEX IF NOT EXISTS idx_active_reminders ON reminders(id) WHERE is_acknowledged = false AND scheduled_time <= NOW();
CREATE INDEX IF NOT EXISTS idx_unresolved_alerts ON alerts(id) WHERE is_resolved = false;

-- Create views for common queries
CREATE OR REPLACE VIEW user_health_summary AS
SELECT
    u.id as user_id,
    u.full_name,
    u.device_id,
    COUNT(hr.id) as total_readings,
    AVG(hr.heart_rate) as avg_heart_rate,
    AVG(hr.blood_pressure_systolic) as avg_bp_systolic,
    AVG(hr.blood_pressure_diastolic) as avg_bp_diastolic,
    AVG(hr.glucose_level) as avg_glucose,
    AVG(hr.oxygen_saturation) as avg_oxygen,
    SUM(CASE WHEN hr.overall_health_alert THEN 1 ELSE 0 END) as total_alerts,
    MAX(hr.timestamp) as last_reading
FROM users u
LEFT JOIN health_records hr ON u.id = hr.user_id
WHERE u.is_active = true
GROUP BY u.id, u.full_name, u.device_id;

CREATE OR REPLACE VIEW user_safety_summary AS
SELECT
    u.id as user_id,
    u.full_name,
    u.device_id,
    COUNT(sr.id) as total_readings,
    SUM(CASE WHEN sr.fall_detected THEN 1 ELSE 0 END) as total_falls,
    SUM(CASE WHEN sr.safety_alert THEN 1 ELSE 0 END) as total_alerts,
    MAX(sr.timestamp) as last_reading,
    STRING_AGG(DISTINCT sr.location_room, ', ') as locations
FROM users u
LEFT JOIN safety_records sr ON u.id = sr.user_id
WHERE u.is_active = true
GROUP BY u.id, u.full_name, u.device_id;

CREATE OR REPLACE VIEW system_dashboard AS
SELECT
    (SELECT COUNT(*) FROM users WHERE is_active = true) as active_users,
    (SELECT COUNT(*) FROM users WHERE role = 'elderly' AND is_active = true) as elderly_users,
    (SELECT COUNT(*) FROM users WHERE role = 'caregiver' AND is_active = true) as caregivers,
    (SELECT COUNT(*) FROM health_records WHERE timestamp >= NOW() - INTERVAL '24 hours') as recent_health_readings,
    (SELECT COUNT(*) FROM safety_records WHERE timestamp >= NOW() - INTERVAL '24 hours') as recent_safety_readings,
    (SELECT COUNT(*) FROM reminders WHERE is_acknowledged = false AND scheduled_time <= NOW()) as pending_reminders,
    (SELECT COUNT(*) FROM alerts WHERE is_resolved = false) as unresolved_alerts,
    (SELECT COUNT(*) FROM safety_records WHERE fall_detected = true AND timestamp >= NOW() - INTERVAL '7 days') as recent_falls;

-- Create function for health trend analysis
CREATE OR REPLACE FUNCTION calculate_health_trend(
    p_user_id INTEGER,
    p_hours INTEGER DEFAULT 24
) RETURNS TABLE (
    metric TEXT,
    current_value NUMERIC,
    previous_avg NUMERIC,
    trend TEXT,
    change_percent NUMERIC
) AS $$
BEGIN
    RETURN QUERY
    WITH current_period AS (
        SELECT
            AVG(heart_rate) as hr_avg,
            AVG(blood_pressure_systolic) as bp_sys_avg,
            AVG(blood_pressure_diastolic) as bp_dia_avg,
            AVG(glucose_level) as glucose_avg,
            AVG(oxygen_saturation) as oxygen_avg
        FROM health_records
        WHERE user_id = p_user_id
        AND timestamp >= NOW() - INTERVAL '1 hour' * p_hours / 2
    ),
    previous_period AS (
        SELECT
            AVG(heart_rate) as hr_avg,
            AVG(blood_pressure_systolic) as bp_sys_avg,
            AVG(blood_pressure_diastolic) as bp_dia_avg,
            AVG(glucose_level) as glucose_avg,
            AVG(oxygen_saturation) as oxygen_avg
        FROM health_records
        WHERE user_id = p_user_id
        AND timestamp >= NOW() - INTERVAL '1 hour' * p_hours
        AND timestamp < NOW() - INTERVAL '1 hour' * p_hours / 2
    )
    SELECT
        'Heart Rate'::TEXT,
        cp.hr_avg,
        pp.hr_avg,
        CASE
            WHEN cp.hr_avg > pp.hr_avg THEN 'increasing'
            WHEN cp.hr_avg < pp.hr_avg THEN 'decreasing'
            ELSE 'stable'
        END,
        CASE
            WHEN pp.hr_avg > 0 THEN ROUND(((cp.hr_avg - pp.hr_avg) / pp.hr_avg) * 100, 2)
            ELSE 0
        END
    FROM current_period cp, previous_period pp
    UNION ALL
    SELECT
        'Blood Pressure Systolic'::TEXT,
        cp.bp_sys_avg,
        pp.bp_sys_avg,
        CASE
            WHEN cp.bp_sys_avg > pp.bp_sys_avg THEN 'increasing'
            WHEN cp.bp_sys_avg < pp.bp_sys_avg THEN 'decreasing'
            ELSE 'stable'
        END,
        CASE
            WHEN pp.bp_sys_avg > 0 THEN ROUND(((cp.bp_sys_avg - pp.bp_sys_avg) / pp.bp_sys_avg) * 100, 2)
            ELSE 0
        END
    FROM current_period cp, previous_period pp
    UNION ALL
    SELECT
        'Blood Pressure Diastolic'::TEXT,
        cp.bp_dia_avg,
        pp.bp_dia_avg,
        CASE
            WHEN cp.bp_dia_avg > pp.bp_dia_avg THEN 'increasing'
            WHEN cp.bp_dia_avg < pp.bp_dia_avg THEN 'decreasing'
            ELSE 'stable'
        END,
        CASE
            WHEN pp.bp_dia_avg > 0 THEN ROUND(((cp.bp_dia_avg - pp.bp_dia_avg) / pp.bp_dia_avg) * 100, 2)
            ELSE 0
        END
    FROM current_period cp, previous_period pp
    UNION ALL
    SELECT
        'Glucose'::TEXT,
        cp.glucose_avg,
        pp.glucose_avg,
        CASE
            WHEN cp.glucose_avg > pp.glucose_avg THEN 'increasing'
            WHEN cp.glucose_avg < pp.glucose_avg THEN 'decreasing'
            ELSE 'stable'
        END,
        CASE
            WHEN pp.glucose_avg > 0 THEN ROUND(((cp.glucose_avg - pp.glucose_avg) / pp.glucose_avg) * 100, 2)
            ELSE 0
        END
    FROM current_period cp, previous_period pp
    UNION ALL
    SELECT
        'Oxygen Saturation'::TEXT,
        cp.oxygen_avg,
        pp.oxygen_avg,
        CASE
            WHEN cp.oxygen_avg > pp.oxygen_avg THEN 'increasing'
            WHEN cp.oxygen_avg < pp.oxygen_avg THEN 'decreasing'
            ELSE 'stable'
        END,
        CASE
            WHEN pp.oxygen_avg > 0 THEN ROUND(((cp.oxygen_avg - pp.oxygen_avg) / pp.oxygen_avg) * 100, 2)
            ELSE 0
        END
    FROM current_period cp, previous_period pp;
END;
$$ LANGUAGE plpgsql;

-- Create function for user activity patterns
CREATE OR REPLACE FUNCTION get_user_activity_pattern(
    p_user_id INTEGER,
    p_days INTEGER DEFAULT 7
) RETURNS TABLE (
    hour_of_day INTEGER,
    activity TEXT,
    count INTEGER,
    percentage NUMERIC
) AS $$
BEGIN
    RETURN QUERY
    WITH hourly_activity AS (
        SELECT
            EXTRACT(HOUR FROM timestamp) as hour,
            COALESCE(movement_activity::TEXT, 'unknown') as activity,
            COUNT(*) as activity_count
        FROM safety_records
        WHERE user_id = p_user_id
        AND timestamp >= NOW() - INTERVAL '1 day' * p_days
        GROUP BY EXTRACT(HOUR FROM timestamp), movement_activity
    ),
    total_by_hour AS (
        SELECT
            hour,
            SUM(activity_count) as total_count
        FROM hourly_activity
        GROUP BY hour
    )
    SELECT
        ha.hour::INTEGER,
        ha.activity,
        ha.activity_count::INTEGER,
        ROUND((ha.activity_count::NUMERIC / th.total_count) * 100, 2)
    FROM hourly_activity ha
    JOIN total_by_hour th ON ha.hour = th.hour
    ORDER BY ha.hour, ha.activity_count DESC;
END;
$$ LANGUAGE plpgsql;

-- Insert default system configuration
INSERT INTO system_configuration (key, value, description) VALUES
('health_alert_thresholds', '{
    "heart_rate_min": 60,
    "heart_rate_max": 100,
    "blood_pressure_systolic_min": 90,
    "blood_pressure_systolic_max": 140,
    "blood_pressure_diastolic_min": 60,
    "blood_pressure_diastolic_max": 90,
    "glucose_min": 70,
    "glucose_max": 140,
    "oxygen_saturation_min": 95
}', 'Health monitoring threshold values'),
('system_settings', '{
    "max_users": 1000,
    "data_retention_days": 365,
    "alert_retry_attempts": 3,
    "reminder_escalation_minutes": 15
}', 'General system configuration'),
('notification_settings', '{
    "email_enabled": true,
    "sms_enabled": true,
    "voice_enabled": true,
    "emergency_contacts_required": 2
}', 'Notification system configuration')
ON CONFLICT (key) DO NOTHING;

-- Create maintenance function
CREATE OR REPLACE FUNCTION cleanup_old_data() RETURNS void AS $$
BEGIN
    -- Delete old health records (keep last 2 years)
    DELETE FROM health_records
    WHERE timestamp < NOW() - INTERVAL '2 years';

    -- Delete old safety records (keep last 1 year)
    DELETE FROM safety_records
    WHERE timestamp < NOW() - INTERVAL '1 year';

    -- Delete old resolved alerts (keep last 6 months)
    DELETE FROM alerts
    WHERE is_resolved = true
    AND resolved_at < NOW() - INTERVAL '6 months';

    -- Delete old completed reminders (keep last 3 months)
    DELETE FROM reminders
    WHERE is_acknowledged = true
    AND acknowledged_at < NOW() - INTERVAL '3 months';

    -- Log cleanup
    INSERT INTO system_configuration (key, value, description)
    VALUES (
        'last_cleanup',
        json_build_object('timestamp', NOW(), 'user', CURRENT_USER),
        'Last data cleanup timestamp'
    )
    ON CONFLICT (key) DO UPDATE SET
        value = json_build_object('timestamp', NOW(), 'user', CURRENT_USER),
        updated_at = NOW();
END;
$$ LANGUAGE plpgsql;

-- Create trigger to update updated_at timestamp
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Apply update trigger to relevant tables
CREATE TRIGGER update_users_updated_at BEFORE UPDATE ON users
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_reminders_updated_at BEFORE UPDATE ON reminders
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_alerts_updated_at BEFORE UPDATE ON alerts
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
