-- iOS flatten SQL (LEFT JOIN version with QUALIFY to dedupe per insight code)
-- NOTE: reference_number assumed unique per partition date.
-- TODO: Parameterize dataset/table/partition externally if needed.
INSERT INTO `TRANS_EDEP_DATASET.TMP_CREDOLAB_DATA_iOS` (
		cuid,
		seriesnumber,
		device_os,
		BQ_UPDATED_TIME,
		PARTITION_DATE,
		requested_date,
		requester,
		reference_number,
		device_id,
		device_brand,
		device_model,
		device_cpu_type,
		device_is_lying,
		device_is_angled,
		device_os_version,
		device_allows_voip,
		device_is_standing,
		device_region_code,
		device_screen_size,
		device_time_zone_id,
		device_allows_voip2,
		device_is_simulator,
		device_currency_code,
		device_is_jailbroken,
		device_language_code,
		device_ram_total_size,
		device_battery_status,
		device_sim_country_iso,
		device_sim_country_iso2,
		device_location_enabled,
		device_main_storage_free,
		device_main_storage_total,
		device_battery_is_charging,
		device_network_operator_name,
		device_network_operator_name2,
		device_locale_display_language,
		device_network_connection_type,
		ip,
		ip_loc,
		ip_city,
		ip_bogon,
		ip_postal,
		ip_region,
		ip_country,
		ip_hostname,
		ip_timezone,
		ip_privacy_tor,
		ip_privacy_vpn,
		ip_privacy_proxy,
		ip_privacy_relay,
		ip_privacy_hosting,
		permission_contacts_usage,
		permission_calendars_usage,
		permission_reminders_usage,
		permission_apple_music_usage,
		permission_photo_library_usage,
		velocity_datasets_count_all_from_ip,
		velocity_datasets_count_all_from_device_id,
		velocity_datasets_unique_device_id_from_ip,
		velocity_datasets_unique_ip_from_device_id,
		velocity_datasets_count_all_from_device_id_and_ip,
		typing_text_input_speed,
		typing_text_input_letters_count,
		typing_text_input_numbers_count,
		typing_input_start_with_lower_count,
		typing_input_start_with_upper_count,
		typing_input_start_with_number_count,
		typing_text_input_chars_except_num_and_letters_count,
		ui_input_delete_actions_count,
		ui_input_insert_actions_count,
		ui_input_delete_text_actions_count,
		ui_input_insert_text_actions_count,
		ui_text_input_text_prefilled_count,
		ui_application_as_background_count,
		ui_application_as_foreground_count,
		ui_text_input_text_removed_all_count,
		ui_client_interactions_time_spent_total,
		ui_client_interactions_tracked_events_count,
		finger_pan_path_length,
		finger_swipe_path_length,
		finger_pan_total_events_count,
		finger_scale_total_events_count,
		finger_swipe_total_events_count,
		finger_touch_total_events_count,
		finger_text_input_total_events_count,
		touch_actions_speed,
		touch_pan_total_number_of_touches_count,
		touch_scale_total_number_of_touches_count,
		anomaly_touch_rage_actions_count,
		anomaly_text_input_rage_actions_count,
		expert_score,
		expert_probability
)
WITH
	json_input AS (
		SELECT
			r.cuid,
			r.series_number,
			r.device_os,
			r.BQ_UPDATED_TIME,
			r.PARTITION_DATE,
			PARSE_JSON(r.raw_data) AS parsed_json
		FROM `RAW_EDEP_DATASET.CREDOLAB_DATA_iOS` r
		LEFT JOIN `TRANS_EDEP_DATASET.TMP_CREDOLAB_DATA_iOS` t 
			ON r.reference_id = t.reference_number
			WHERE r.reference_id IS NOT NULL 
			AND t.reference_number IS NULL
      		QUALIFY ROW_NUMBER() OVER (PARTITION BY r.reference_id ORDER BY PARTITION_DATE DESC) = 1

	),
	base_metadata AS (
		SELECT
			CAST(cuid AS STRING) AS cuid,
			CAST(series_number AS STRING) AS seriesnumber,
			CAST(device_os AS STRING) AS device_os,
			BQ_UPDATED_TIME,
			PARTITION_DATE,
			CAST(JSON_VALUE(parsed_json, '$.requestedDate') AS STRING) AS requested_date,
			CAST(JSON_VALUE(parsed_json, '$.requester') AS STRING) AS requester,
			CAST(JSON_VALUE(parsed_json, '$.referenceNumber') AS STRING) AS reference_number
		FROM json_input
	),
	insights AS (
		SELECT
			JSON_VALUE(parsed_json, '$.referenceNumber') AS reference_number,
			JSON_VALUE(i, '$.code') AS code,
			JSON_VALUE(i, '$.calculatedDate') AS calculated_date,
			JSON_QUERY(i, '$.value') AS value
		FROM json_input, UNNEST(JSON_QUERY_ARRAY(parsed_json, '$.insights')) AS i
	),
	deviceInfo AS (
		SELECT reference_number,
			CAST(JSON_VALUE(value, '$.deviceId') AS STRING) AS device_id,
			CAST(JSON_VALUE(value, '$.deviceBrand') AS STRING) AS device_brand,
			CAST(JSON_VALUE(value, '$.deviceModel') AS STRING) AS device_model,
			CAST(JSON_VALUE(value, '$.deviceCPUType') AS STRING) AS device_cpu_type,
			CAST(JSON_VALUE(value, '$.deviceIsLying') AS STRING) AS device_is_lying,
			CAST(JSON_VALUE(value, '$.deviceIsAngled') AS STRING) AS device_is_angled,
			CAST(JSON_VALUE(value, '$.deviceOsVersion') AS STRING) AS device_os_version,
			CAST(JSON_VALUE(value, '$.deviceAllowsVOIP') AS STRING) AS device_allows_voip,
			CAST(JSON_VALUE(value, '$.deviceIsStanding') AS STRING) AS device_is_standing,
			CAST(JSON_VALUE(value, '$.deviceRegionCode') AS STRING) AS device_region_code,
			CAST(JSON_VALUE(value, '$.deviceScreenSize') AS STRING) AS device_screen_size,
			CAST(JSON_VALUE(value, '$.deviceTimeZoneId') AS STRING) AS device_time_zone_id,
			CAST(JSON_VALUE(value, '$.deviceAllowsVOIP2') AS STRING) AS device_allows_voip2,
			CAST(JSON_VALUE(value, '$.deviceIsSimulator') AS STRING) AS device_is_simulator,
			CAST(JSON_VALUE(value, '$.deviceCurrencyCode') AS STRING) AS device_currency_code,
			CAST(JSON_VALUE(value, '$.deviceIsJailBroken') AS STRING) AS device_is_jailbroken,
			CAST(JSON_VALUE(value, '$.deviceLanguageCode') AS STRING) AS device_language_code,
			CAST(JSON_VALUE(value, '$.deviceRamTotalSize') AS STRING) AS device_ram_total_size,
			CAST(JSON_VALUE(value, '$.deviceBatteryStatus') AS STRING) AS device_battery_status,
			CAST(JSON_VALUE(value, '$.deviceSimCountryIso') AS STRING) AS device_sim_country_iso,
			CAST(JSON_VALUE(value, '$.deviceSimCountryIso2') AS STRING) AS device_sim_country_iso2,
			CAST(JSON_VALUE(value, '$.deviceLocationEnabled') AS STRING) AS device_location_enabled,
			CAST(JSON_VALUE(value, '$.deviceMainStorageFree') AS STRING) AS device_main_storage_free,
			CAST(JSON_VALUE(value, '$.deviceMainStorageTotal') AS STRING) AS device_main_storage_total,
			CAST(JSON_VALUE(value, '$.deviceBatteryIsCharging') AS STRING) AS device_battery_is_charging,
			CAST(JSON_VALUE(value, '$.deviceNetworkOperatorName') AS STRING) AS device_network_operator_name,
			CAST(JSON_VALUE(value, '$.deviceNetworkOperatorName2') AS STRING) AS device_network_operator_name2,
			CAST(JSON_VALUE(value, '$.deviceLocaleDisplayLanguage') AS STRING) AS device_locale_display_language,
			CAST(JSON_VALUE(value, '$.deviceNetworkConnectionType') AS STRING) AS device_network_connection_type,
			ROW_NUMBER() OVER (PARTITION BY reference_number ORDER BY calculated_date DESC) rn
		FROM insights WHERE code = 'deviceInfo'
		QUALIFY rn = 1
	),
	ipInfo AS (
		SELECT reference_number,
			CAST(JSON_VALUE(value, '$.ip') AS STRING) AS ip,
			CAST(JSON_VALUE(value, '$.loc') AS STRING) AS ip_loc,
			CAST(JSON_VALUE(value, '$.city') AS STRING) AS ip_city,
			CAST(JSON_VALUE(value, '$.bogon') AS STRING) AS ip_bogon,
			CAST(JSON_VALUE(value, '$.postal') AS STRING) AS ip_postal,
			CAST(JSON_VALUE(value, '$.region') AS STRING) AS ip_region,
			CAST(JSON_VALUE(value, '$.country') AS STRING) AS ip_country,
			CAST(JSON_VALUE(value, '$.hostname') AS STRING) AS ip_hostname,
			CAST(JSON_VALUE(value, '$.timezone') AS STRING) AS ip_timezone,
			CAST(JSON_VALUE(value, '$.privacyTor') AS STRING) AS ip_privacy_tor,
			CAST(JSON_VALUE(value, '$.privacyVpn') AS STRING) AS ip_privacy_vpn,
			CAST(JSON_VALUE(value, '$.privacyProxy') AS STRING) AS ip_privacy_proxy,
			CAST(JSON_VALUE(value, '$.privacyRelay') AS STRING) AS ip_privacy_relay,
			CAST(JSON_VALUE(value, '$.privacyHosting') AS STRING) AS ip_privacy_hosting,
			ROW_NUMBER() OVER (PARTITION BY reference_number ORDER BY calculated_date DESC) rn
		FROM insights WHERE code = 'ipInfo'
		QUALIFY rn = 1
	),
	permissions AS (
		SELECT reference_number,
			CAST(JSON_VALUE(value, '$.NSContactsUsageDescription') AS STRING) AS permission_contacts_usage,
			CAST(JSON_VALUE(value, '$.NSCalendarsUsageDescription') AS STRING) AS permission_calendars_usage,
			CAST(JSON_VALUE(value, '$.NSRemindersUsageDescription') AS STRING) AS permission_reminders_usage,
			CAST(JSON_VALUE(value, '$.NSAppleMusicUsageDescription') AS STRING) AS permission_apple_music_usage,
			CAST(JSON_VALUE(value, '$.NSPhotoLibraryUsageDescription') AS STRING) AS permission_photo_library_usage,
			ROW_NUMBER() OVER (PARTITION BY reference_number ORDER BY calculated_date DESC) rn
		FROM insights WHERE code = 'permissions'
		QUALIFY rn = 1
	),
	velocity AS (
		SELECT reference_number,
			-- 支援兩種欄位命名 (AllFrom / From...LastYear) 取其一
			CAST(COALESCE(JSON_VALUE(value, '$.datasetsCountAllFromIp'), JSON_VALUE(value, '$.datasetsCountFromIpLastYear')) AS STRING) AS velocity_datasets_count_all_from_ip,
			CAST(COALESCE(JSON_VALUE(value, '$.datasetsCountAllFromDeviceId'), JSON_VALUE(value, '$.datasetsCountFromDeviceIdLastYear')) AS STRING) AS velocity_datasets_count_all_from_device_id,
			CAST(COALESCE(JSON_VALUE(value, '$.datasetsUniqueDeviceIdFromIp'), JSON_VALUE(value, '$.datasetsUniqueDeviceIdFromIpLastYear')) AS STRING) AS velocity_datasets_unique_device_id_from_ip,
			CAST(COALESCE(JSON_VALUE(value, '$.datasetsUniqueIpFromDeviceId'), JSON_VALUE(value, '$.datasetsUniqueIpFromDeviceIdLastYear')) AS STRING) AS velocity_datasets_unique_ip_from_device_id,
			CAST(COALESCE(JSON_VALUE(value, '$.datasetsCountAllFromDeviceIdAndIp'), JSON_VALUE(value, '$.datasetsCountFromDeviceIdAndIpLastYear')) AS STRING) AS velocity_datasets_count_all_from_device_id_and_ip,
			ROW_NUMBER() OVER (PARTITION BY reference_number ORDER BY calculated_date DESC) rn
		FROM insights WHERE code = 'velocity'
		QUALIFY rn = 1
	),
	typing AS (
		SELECT reference_number,
			CAST(JSON_VALUE(value, '$.textInputSpeed') AS STRING) AS typing_text_input_speed,
			CAST(JSON_VALUE(value, '$.textInputLettersCount') AS STRING) AS typing_text_input_letters_count,
			CAST(JSON_VALUE(value, '$.textInputNumbersCount') AS STRING) AS typing_text_input_numbers_count,
			CAST(JSON_VALUE(value, '$.inputStartWithLowerCount') AS STRING) AS typing_input_start_with_lower_count,
			CAST(JSON_VALUE(value, '$.inputStartWithUpperCount') AS STRING) AS typing_input_start_with_upper_count,
			CAST(JSON_VALUE(value, '$.inputStartWithNumberCount') AS STRING) AS typing_input_start_with_number_count,
			CAST(JSON_VALUE(value, '$.textInputCharsExceptNumAndLettersCount') AS STRING) AS typing_text_input_chars_except_num_and_letters_count,
			ROW_NUMBER() OVER (PARTITION BY reference_number ORDER BY calculated_date DESC) rn
		FROM insights WHERE code = 'typing'
		QUALIFY rn = 1
	),
	uiInteractions AS (
		SELECT reference_number,
			CAST(JSON_VALUE(value, '$.inputDeleteActionsCount') AS STRING) AS ui_input_delete_actions_count,
			CAST(JSON_VALUE(value, '$.inputInsertActionsCount') AS STRING) AS ui_input_insert_actions_count,
			CAST(JSON_VALUE(value, '$.inputDeleteTextActionsCount') AS STRING) AS ui_input_delete_text_actions_count,
			CAST(JSON_VALUE(value, '$.inputInsertTextActionsCount') AS STRING) AS ui_input_insert_text_actions_count,
			CAST(JSON_VALUE(value, '$.textInputTextPrefilledCount') AS STRING) AS ui_text_input_text_prefilled_count,
			CAST(JSON_VALUE(value, '$.applicationAsBackgroundCount') AS STRING) AS ui_application_as_background_count,
			CAST(JSON_VALUE(value, '$.applicationAsForegroundCount') AS STRING) AS ui_application_as_foreground_count,
			CAST(JSON_VALUE(value, '$.textInputTextRemovedAllCount') AS STRING) AS ui_text_input_text_removed_all_count,
			CAST(JSON_VALUE(value, '$.clientInteractionsTimeSpentTotal') AS STRING) AS ui_client_interactions_time_spent_total,
			CAST(JSON_VALUE(value, '$.clientInteractionsTrackedEventsCount') AS STRING) AS ui_client_interactions_tracked_events_count,
			ROW_NUMBER() OVER (PARTITION BY reference_number ORDER BY calculated_date DESC) rn
		FROM insights WHERE code = 'uiInteractions'
		QUALIFY rn = 1
	),
	fingerGestures AS (
		SELECT reference_number,
			CAST(JSON_VALUE(value, '$.panPathLength') AS STRING) AS finger_pan_path_length,
			CAST(JSON_VALUE(value, '$.swipePathLength') AS STRING) AS finger_swipe_path_length,
			CAST(JSON_VALUE(value, '$.panTotalEventsCount') AS STRING) AS finger_pan_total_events_count,
			CAST(JSON_VALUE(value, '$.scaleTotalEventsCount') AS STRING) AS finger_scale_total_events_count,
			CAST(JSON_VALUE(value, '$.swipeTotalEventsCount') AS STRING) AS finger_swipe_total_events_count,
			CAST(JSON_VALUE(value, '$.touchTotalEventsCount') AS STRING) AS finger_touch_total_events_count,
			CAST(JSON_VALUE(value, '$.textInputTotalEventsCount') AS STRING) AS finger_text_input_total_events_count,
			ROW_NUMBER() OVER (PARTITION BY reference_number ORDER BY calculated_date DESC) rn
		FROM insights WHERE code = 'fingerGestures'
		QUALIFY rn = 1
	),
	touchActions AS (
		SELECT reference_number,
			CAST(JSON_VALUE(value, '$.touchActionsSpeed') AS STRING) AS touch_actions_speed,
			CAST(JSON_VALUE(value, '$.panTotalNumberOfTouchesCount') AS STRING) AS touch_pan_total_number_of_touches_count,
			CAST(JSON_VALUE(value, '$.scaleTotalNumberOfTouchesCount') AS STRING) AS touch_scale_total_number_of_touches_count,
			ROW_NUMBER() OVER (PARTITION BY reference_number ORDER BY calculated_date DESC) rn
		FROM insights WHERE code = 'touchActions'
		QUALIFY rn = 1
	),
	anomaly AS (
		SELECT reference_number,
			CAST(JSON_VALUE(value, '$.touchRageActionsCount') AS STRING) AS anomaly_touch_rage_actions_count,
			CAST(JSON_VALUE(value, '$.textInputRageActionsCount') AS STRING) AS anomaly_text_input_rage_actions_count,
			ROW_NUMBER() OVER (PARTITION BY reference_number ORDER BY calculated_date DESC) rn
		FROM insights WHERE code = 'anomaly'
		QUALIFY rn = 1
	),
	expertScore AS (
		SELECT reference_number,
			CAST(JSON_VALUE(value, '$.score') AS STRING) AS expert_score,
			CAST(JSON_VALUE(value, '$.probability') AS STRING) AS expert_probability,
			ROW_NUMBER() OVER (PARTITION BY reference_number ORDER BY calculated_date DESC) rn
		FROM insights WHERE code = 'expertScore'
		QUALIFY rn = 1
	)
SELECT
	b.cuid,
	b.seriesnumber,
	b.device_os,
	b.BQ_UPDATED_TIME,
	b.PARTITION_DATE,
	b.requested_date,
	b.requester,
	b.reference_number,
	d.device_id,
	d.device_brand,
	d.device_model,
	d.device_cpu_type,
	d.device_is_lying,
	d.device_is_angled,
	d.device_os_version,
	d.device_allows_voip,
	d.device_is_standing,
	d.device_region_code,
	d.device_screen_size,
	d.device_time_zone_id,
	d.device_allows_voip2,
	d.device_is_simulator,
	d.device_currency_code,
	d.device_is_jailbroken,
	d.device_language_code,
	d.device_ram_total_size,
	d.device_battery_status,
	d.device_sim_country_iso,
	d.device_sim_country_iso2,
	d.device_location_enabled,
	d.device_main_storage_free,
	d.device_main_storage_total,
	d.device_battery_is_charging,
	d.device_network_operator_name,
	d.device_network_operator_name2,
	d.device_locale_display_language,
	d.device_network_connection_type,
	i.ip,
	i.ip_loc,
	i.ip_city,
	i.ip_bogon,
	i.ip_postal,
	i.ip_region,
	i.ip_country,
	i.ip_hostname,
	i.ip_timezone,
	i.ip_privacy_tor,
	i.ip_privacy_vpn,
	i.ip_privacy_proxy,
	i.ip_privacy_relay,
	i.ip_privacy_hosting,
	p.permission_contacts_usage,
	p.permission_calendars_usage,
	p.permission_reminders_usage,
	p.permission_apple_music_usage,
	p.permission_photo_library_usage,
	v.velocity_datasets_count_all_from_ip,
	v.velocity_datasets_count_all_from_device_id,
	v.velocity_datasets_unique_device_id_from_ip,
	v.velocity_datasets_unique_ip_from_device_id,
	v.velocity_datasets_count_all_from_device_id_and_ip,
	t.typing_text_input_speed,
	t.typing_text_input_letters_count,
	t.typing_text_input_numbers_count,
	t.typing_input_start_with_lower_count,
	t.typing_input_start_with_upper_count,
	t.typing_input_start_with_number_count,
	t.typing_text_input_chars_except_num_and_letters_count,
	u.ui_input_delete_actions_count,
	u.ui_input_insert_actions_count,
	u.ui_input_delete_text_actions_count,
	u.ui_input_insert_text_actions_count,
	u.ui_text_input_text_prefilled_count,
	u.ui_application_as_background_count,
	u.ui_application_as_foreground_count,
	u.ui_text_input_text_removed_all_count,
	u.ui_client_interactions_time_spent_total,
	u.ui_client_interactions_tracked_events_count,
	f.finger_pan_path_length,
	f.finger_swipe_path_length,
	f.finger_pan_total_events_count,
	f.finger_scale_total_events_count,
	f.finger_swipe_total_events_count,
	f.finger_touch_total_events_count,
	f.finger_text_input_total_events_count,
	ta.touch_actions_speed,
	ta.touch_pan_total_number_of_touches_count,
	ta.touch_scale_total_number_of_touches_count,
	a.anomaly_touch_rage_actions_count,
	a.anomaly_text_input_rage_actions_count,
	e.expert_score,
	e.expert_probability
FROM base_metadata b
	LEFT JOIN deviceInfo d ON b.reference_number = d.reference_number
	LEFT JOIN ipInfo i ON b.reference_number = i.reference_number
	LEFT JOIN permissions p ON b.reference_number = p.reference_number
	LEFT JOIN velocity v ON b.reference_number = v.reference_number
	LEFT JOIN typing t ON b.reference_number = t.reference_number
	LEFT JOIN uiInteractions u ON b.reference_number = u.reference_number
	LEFT JOIN fingerGestures f ON b.reference_number = f.reference_number
	LEFT JOIN touchActions ta ON b.reference_number = ta.reference_number
	LEFT JOIN anomaly a ON b.reference_number = a.reference_number
	LEFT JOIN expertScore e ON b.reference_number = e.reference_number;
