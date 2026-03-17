-- =============================================================================
-- Intelligence Module Registration
-- =============================================================================
-- Register Intelligence Module in the marketplace_modules table
-- NOTE: This module is backend-only (no frontend), so remote_entry_url, scope,
-- and exposed_module are NULL. Make sure these columns allow NULL:
--   ALTER TABLE marketplace_modules ALTER COLUMN remote_entry_url DROP NOT NULL;
--   ALTER TABLE marketplace_modules ALTER COLUMN scope DROP NOT NULL;
--   ALTER TABLE marketplace_modules ALTER COLUMN exposed_module DROP NOT NULL;
-- =============================================================================

INSERT INTO marketplace_modules (
    id,
    name,
    display_name,
    description,
    remote_entry_url,
    scope,
    exposed_module,
    version,
    author,
    category,
    route_path,
    label,
    module_type,
    required_plan_type,
    pricing_tier,
    is_local,
    is_active,
    required_roles,
    icon_url,
    metadata
) VALUES (
    'intelligence',
    'intelligence',
    'Intelligence Module',
    'AI/ML Intelligence Module - Analysis and Prediction Service for Nekazari Platform',
    NULL,  -- Backend-only module, no frontend
    NULL,  -- Backend-only module
    NULL,  -- Backend-only module
    '1.0.0',
    'Nekazari Team',
    'analytics',
    '/intelligence',
    'Intelligence',
    'ADDON_PAID',
    'premium',
    'PAID',
    false,
    true,
    ARRAY['Farmer', 'TenantAdmin', 'PlatformAdmin'],
    'https://YOUR_CDN_OR_DOMAIN/module-icons/intelligence.svg',
    '{"icon": "🧠", "color": "#8B5CF6", "features": ["AI-powered predictions", "Time series analysis", "ML model integration"]}'::jsonb
) ON CONFLICT (id) DO UPDATE SET
    display_name = EXCLUDED.display_name,
    description = EXCLUDED.description,
    version = EXCLUDED.version,
    is_active = true,
    updated_at = NOW();


