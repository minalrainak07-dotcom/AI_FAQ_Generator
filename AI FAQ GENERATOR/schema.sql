-- AI FAQ Generator Database Schema
CREATE DATABASE IF NOT EXISTS ai_faq_generator CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE ai_faq_generator;

CREATE TABLE IF NOT EXISTS faq_generations (
    id INT AUTO_INCREMENT PRIMARY KEY,
    title VARCHAR(500) NOT NULL,
    source_type ENUM('pdf', 'text', 'topic') NOT NULL,
    source_filename VARCHAR(255) DEFAULT NULL,
    source_text LONGTEXT DEFAULT NULL,
    difficulty VARCHAR(50) DEFAULT 'intermediate',
    answer_length VARCHAR(50) DEFAULT 'medium',
    language VARCHAR(50) DEFAULT 'English',
    category VARCHAR(100) DEFAULT 'General Knowledge',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS faqs (
    id INT AUTO_INCREMENT PRIMARY KEY,
    generation_id INT NOT NULL,
    question TEXT NOT NULL,
    answer TEXT NOT NULL,
    category VARCHAR(100) DEFAULT 'General',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (generation_id) REFERENCES faq_generations(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
