CREATE DATABASE IF NOT EXISTS powerwise
  CHARACTER SET utf8mb4
  COLLATE utf8mb4_unicode_ci;
USE powerwise;

CREATE TABLE IF NOT EXISTS users (
  id INT AUTO_INCREMENT PRIMARY KEY,
  name VARCHAR(100) NOT NULL,
  email VARCHAR(254) NOT NULL UNIQUE,
  password_hash VARCHAR(255) NOT NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  INDEX ix_users_email (email)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS appliances (
  id INT AUTO_INCREMENT PRIMARY KEY,
  user_id INT NOT NULL,
  name VARCHAR(100) NOT NULL,
  category VARCHAR(60) NOT NULL,
  power_w DOUBLE NOT NULL,
  daily_hours DOUBLE NOT NULL,
  quantity INT NOT NULL DEFAULT 1,
  is_on BOOLEAN NOT NULL DEFAULT FALSE,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  INDEX ix_appliances_user_id (user_id),
  CONSTRAINT fk_appliances_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS consumption_records (
  id INT AUTO_INCREMENT PRIMARY KEY,
  user_id INT NOT NULL,
  appliance_id INT NULL,
  energy_kwh DOUBLE NOT NULL,
  power_w DOUBLE NULL,
  duration_hours DOUBLE NULL,
  source VARCHAR(20) NOT NULL DEFAULT 'manual',
  recorded_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  INDEX ix_consumption_user_id (user_id),
  INDEX ix_consumption_recorded_at (recorded_at),
  CONSTRAINT fk_consumption_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
  CONSTRAINT fk_consumption_appliance FOREIGN KEY (appliance_id) REFERENCES appliances(id) ON DELETE SET NULL
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS tariff_slabs (
  id INT AUTO_INCREMENT PRIMARY KEY,
  user_id INT NOT NULL,
  lower_units DOUBLE NOT NULL,
  upper_units DOUBLE NULL,
  rate_per_unit DOUBLE NOT NULL,
  `order` INT NOT NULL,
  UNIQUE KEY uq_tariff_user_order (user_id, `order`),
  INDEX ix_tariff_user_id (user_id),
  CONSTRAINT fk_tariff_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS billing_records (
  id INT AUTO_INCREMENT PRIMARY KEY,
  user_id INT NOT NULL,
  period_start DATE NOT NULL,
  period_end DATE NOT NULL,
  units DOUBLE NOT NULL,
  fixed_charges DOUBLE NOT NULL DEFAULT 0,
  additional_charges DOUBLE NOT NULL DEFAULT 0,
  tax_percent DOUBLE NOT NULL DEFAULT 0,
  total_amount DOUBLE NOT NULL,
  breakdown_json JSON NOT NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  INDEX ix_billing_user_id (user_id),
  CONSTRAINT fk_billing_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS usage_limits (
  id INT AUTO_INCREMENT PRIMARY KEY,
  user_id INT NOT NULL,
  period VARCHAR(10) NOT NULL,
  limit_kwh DOUBLE NOT NULL,
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  UNIQUE KEY uq_usage_limit_user_period (user_id, period),
  INDEX ix_usage_limits_user_id (user_id),
  CONSTRAINT fk_usage_limits_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS alerts (
  id INT AUTO_INCREMENT PRIMARY KEY,
  user_id INT NOT NULL,
  period VARCHAR(10) NOT NULL,
  period_key VARCHAR(20) NOT NULL,
  threshold VARCHAR(20) NOT NULL,
  severity VARCHAR(20) NOT NULL,
  description VARCHAR(500) NOT NULL,
  is_read BOOLEAN NOT NULL DEFAULT FALSE,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE KEY uq_alert_threshold_event (user_id, period, period_key, threshold),
  INDEX ix_alerts_user_id (user_id),
  CONSTRAINT fk_alerts_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS energy_recommendations (
  id INT AUTO_INCREMENT PRIMARY KEY,
  user_id INT NOT NULL,
  title VARCHAR(160) NOT NULL,
  description VARCHAR(500) NOT NULL,
  estimated_saving_kwh DOUBLE NULL,
  estimated_saving_amount DOUBLE NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  INDEX ix_recommendations_user_id (user_id),
  CONSTRAINT fk_recommendations_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS devices (
  id INT AUTO_INCREMENT PRIMARY KEY,
  user_id INT NOT NULL,
  name VARCHAR(100) NOT NULL,
  token_hash VARCHAR(255) NOT NULL UNIQUE,
  is_active BOOLEAN NOT NULL DEFAULT TRUE,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  INDEX ix_devices_user_id (user_id),
  CONSTRAINT fk_devices_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
) ENGINE=InnoDB;
