"""Decodifica dei pacchetti UDP di F1 25, formato 2026 (2026 Season Pack) e 2025 (riserva).

Fonte delle strutture: la specifica ufficiale EA («EA SPORTS F1 25 2026 Season Pack UDP
Specification», forums.ea.com, non leggibile in automatico il 19/11/2026), ricopiata dalla
libreria aperta `f1-packets` (PyPI, MIT, versioni 2026.1.1 e 2025.1.1), che genera le
strutture dallo `spec.h` ufficiale. Le taglie del 2025 coincidono con quelle note della
specifica (vedi `prove/prova_pacchetti.py`).

Tutto little-endian, impacchettato (pack 1). Si decodificano solo i pacchetti che servono
all'ingegnere; gli altri si riconoscono dall'intestazione e si ignorano.
"""

import ctypes

FORMATI = (2026, 2025)

# id dei pacchetti
MOTION, SESSION, LAP, EVENT, PARTICIPANTS, SETUPS, TELEMETRY, STATUS, FINAL, LOBBY, \
    DAMAGE, HISTORY, TYRESETS, MOTIONEX, TIMETRIAL, LAPPOS, TELEMETRY2 = range(17)

NOMI = {0: "motion", 1: "session", 2: "lap", 3: "event", 4: "participants", 5: "setups",
        6: "telemetry", 7: "status", 8: "final", 9: "lobby", 10: "damage", 11: "history",
        12: "tyresets", 13: "motionex", 14: "timetrial", 15: "lappos", 16: "telemetry2"}


class _S(ctypes.LittleEndianStructure):
    _pack_ = 1


class Header(_S):
    _fields_ = [
        ("packet_format", ctypes.c_uint16),
        ("game_year", ctypes.c_uint8),
        ("game_major_version", ctypes.c_uint8),
        ("game_minor_version", ctypes.c_uint8),
        ("packet_version", ctypes.c_uint8),
        ("packet_id", ctypes.c_uint8),
        ("session_uid", ctypes.c_uint64),
        ("session_time", ctypes.c_float),
        ("frame_identifier", ctypes.c_uint32),
        ("overall_frame_identifier", ctypes.c_uint32),
        ("player_car_index", ctypes.c_uint8),
        ("secondary_player_car_index", ctypes.c_uint8),
    ]


HEADER_SIZE = ctypes.sizeof(Header)  # 29


def _struct(nome, campi):
    return type(nome, (_S,), {"_fields_": campi})


def _definisci(formato):
    """Crea le strutture per un formato (2026 o 2025)."""
    n = 24 if formato == 2026 else 22
    u8, i8, u16, i16, u32, f32, f64 = (ctypes.c_uint8, ctypes.c_int8, ctypes.c_uint16,
                                        ctypes.c_int16, ctypes.c_uint32, ctypes.c_float,
                                        ctypes.c_double)
    idt = u16 if formato == 2026 else u8  # driver/network/team id: 16 bit dal 2026
    gforce = i16 if formato == 2026 else f32
    S = {}

    car_motion = _struct("CarMotion", [
        ("world_position_x", f32), ("world_position_y", f32), ("world_position_z", f32),
        ("world_velocity_x", f32), ("world_velocity_y", f32), ("world_velocity_z", f32),
        ("world_forward_dir_x", i16), ("world_forward_dir_y", i16), ("world_forward_dir_z", i16),
        ("world_right_dir_x", i16), ("world_right_dir_y", i16), ("world_right_dir_z", i16),
        ("g_force_lateral", gforce), ("g_force_longitudinal", gforce), ("g_force_vertical", gforce),
        ("yaw", f32), ("pitch", f32), ("roll", f32)])
    S[MOTION] = _struct("Motion", [("header", Header), ("cars", car_motion * n)])

    marshal = _struct("Marshal", [("zone_start", f32), ("zone_flag", i8)])
    zona = _struct("Zona", [("zone_start", f32), ("zone_end", f32)])
    meteo = _struct("Meteo", [
        ("session_type", u8), ("time_offset", u8), ("weather", u8),
        ("track_temperature", i8), ("track_temperature_change", i8),
        ("air_temperature", i8), ("air_temperature_change", i8), ("rain_percentage", u8)])
    sess = [
        ("header", Header), ("weather", u8), ("track_temperature", i8), ("air_temperature", i8),
        ("total_laps", u8), ("track_length", u16), ("session_type", u8), ("track_id", i8),
        ("formula", u8), ("session_time_left", u16), ("session_duration", u16),
        ("pit_speed_limit", u8), ("game_paused", u8), ("is_spectating", u8),
        ("spectator_car_index", u8), ("sli_pro_native_support", u8), ("num_marshal_zones", u8),
        ("marshal_zones", marshal * 21), ("safety_car_status", u8), ("network_game", u8),
        ("num_weather_forecast_samples", u8), ("weather_forecast_samples", meteo * 64),
        ("forecast_accuracy", u8), ("ai_difficulty", u8), ("season_link_identifier", u32),
        ("weekend_link_identifier", u32), ("session_link_identifier", u32),
        ("pit_stop_window_ideal_lap", u8), ("pit_stop_window_latest_lap", u8),
        ("pit_stop_rejoin_position", u8), ("steering_assist", u8), ("braking_assist", u8),
        ("gearbox_assist", u8), ("pit_assist", u8), ("pit_release_assist", u8),
        ("ers_assist", u8), ("drs_assist", u8), ("dynamic_racing_line", u8),
        ("dynamic_racing_line_type", u8), ("game_mode", u8), ("rule_set", u8),
        ("time_of_day", u32), ("session_length", u8), ("speed_units_lead_player", u8),
        ("temperature_units_lead_player", u8), ("speed_units_secondary_player", u8),
        ("temperature_units_secondary_player", u8), ("num_safety_car_periods", u8),
        ("num_virtual_safety_car_periods", u8), ("num_red_flag_periods", u8),
        ("equal_car_performance", u8), ("recovery_mode", u8), ("flashback_limit", u8),
        ("surface_type", u8), ("low_fuel_mode", u8), ("race_starts", u8),
        ("tyre_temperature", u8), ("pit_lane_tyre_sim", u8), ("car_damage", u8),
        ("car_damage_rate", u8), ("collisions", u8), ("collisions_off_for_first_lap_only", u8),
        ("mp_unsafe_pit_release", u8), ("mp_off_for_griefing", u8),
        ("corner_cutting_stringency", u8), ("parc_ferme_rules", u8),
        ("pit_stop_experience", u8), ("safety_car", u8), ("safety_car_experience", u8),
        ("formation_lap", u8), ("formation_lap_experience", u8), ("red_flags", u8),
        ("affects_licence_level_solo", u8), ("affects_licence_level_mp", u8),
        ("num_sessions_in_weekend", u8), ("weekend_structure", u8 * 12),
        ("sector2_lap_distance_start", f32), ("sector3_lap_distance_start", f32)]
    if formato == 2026:
        sess += [
            ("active_aero_track_status", u8), ("num_active_aero_zones_full", u8),
            ("active_aero_zones_full", zona * 8), ("num_active_aero_zones_partial", u8),
            ("active_aero_zones_partial", zona * 8), ("num_drs_zones", u8),
            ("drs_zones", zona * 4), ("start_reaction_time", f32),
            ("anti_lock_brakes_assist", u8), ("traction_control_assist", u8),
            ("dynamic_racing_line_hi_vis", u8), ("dynamic_racing_line_colour_blind", u8),
            ("recurring_rewind_prompt", u8)]
    S[SESSION] = _struct("Session", sess)

    lap = _struct("Lap", [
        ("last_lap_time_in_ms", u32), ("current_lap_time_in_ms", u32),
        ("sector1_time_ms_part", u16), ("sector1_time_minutes_part", u8),
        ("sector2_time_ms_part", u16), ("sector2_time_minutes_part", u8),
        ("delta_to_car_in_front_ms_part", u16), ("delta_to_car_in_front_minutes_part", u8),
        ("delta_to_race_leader_ms_part", u16), ("delta_to_race_leader_minutes_part", u8),
        ("lap_distance", f32), ("total_distance", f32), ("safety_car_delta", f32),
        ("car_position", u8), ("current_lap_num", u8), ("pit_status", u8),
        ("num_pit_stops", u8), ("sector", u8), ("current_lap_invalid", u8), ("penalties", u8),
        ("total_warnings", u8), ("corner_cutting_warnings", u8),
        ("num_unserved_drive_through_pens", u8), ("num_unserved_stop_go_pens", u8),
        ("grid_position", u8), ("driver_status", u8), ("result_status", u8),
        ("pit_lane_timer_active", u8), ("pit_lane_time_in_lane_in_ms", u16),
        ("pit_stop_timer_in_ms", u16), ("pit_stop_should_serve_pen", u8),
        ("speed_trap_fastest_speed", f32), ("speed_trap_fastest_lap", u8)])
    S[LAP] = _struct("LapP", [("header", Header), ("cars", lap * n),
                              ("time_trial_pb_car_idx", u8), ("time_trial_rival_car_idx", u8)])

    det = {
        "fastest_lap": _struct("E1", [("vehicle_idx", u8), ("lap_time", f32)]),
        "retirement": _struct("E2", [("vehicle_idx", u8), ("reason", u8)]),
        "drs_disabled": _struct("E3", [("reason", u8)]),
        "team_mate_in_pits": _struct("E4", [("vehicle_idx", u8)]),
        "race_winner": _struct("E5", [("vehicle_idx", u8)]),
        "penalty": _struct("E6", [
            ("penalty_type", u8), ("infringement_type", u8), ("vehicle_idx", u8),
            ("other_vehicle_idx", u8), ("time", u8), ("lap_num", u8), ("places_gained", u8)]),
        "speed_trap": _struct("E7", [
            ("vehicle_idx", u8), ("speed", f32), ("is_overall_fastest_in_session", u8),
            ("is_driver_fastest_in_session", u8), ("fastest_vehicle_idx_in_session", u8),
            ("fastest_speed_in_session", f32)]),
        "start_lights": _struct("E8", [("num_lights", u8)]),
        "drive_through_served": _struct("E9", [("vehicle_idx", u8)]),
        "stop_go_served": _struct("E10", [("vehicle_idx", u8), ("stop_time", f32)]),
        "flashback": _struct("E11", [("flashback_frame_identifier", u32),
                                      ("flashback_session_time", f32)]),
        "buttons": _struct("E12", [("button_status", u32)]),
        "overtake": _struct("E13", [("overtaking_vehicle_idx", u8),
                                     ("being_overtaken_vehicle_idx", u8)]),
        "safety_car": _struct("E14", [("safety_car_type", u8), ("event_type", u8)]),
        "collision": _struct("E15", [("vehicle1_idx", u8), ("vehicle2_idx", u8)]
                             + ([("severity", u8)] if formato == 2026 else [])),
    }
    S["dettagli"] = det
    unione = type("Dettagli", (ctypes.Union,), {"_pack_": 1, "_fields_": list(det.items())})
    S[EVENT] = _struct("Event", [("header", Header), ("code", u8 * 4), ("details", unione)])

    colore = _struct("Colore", [("red", u8), ("green", u8), ("blue", u8)])
    part = _struct("Part", [
        ("ai_controlled", u8), ("driver_id", idt), ("network_id", idt), ("team_id", idt),
        ("my_team", u8), ("race_number", u8), ("nationality", u8), ("name", ctypes.c_char * 32),
        ("your_telemetry", u8), ("show_online_names", u8), ("tech_level", u16),
        ("platform", u8), ("num_colours", u8), ("livery_colours", colore * 4)])
    S[PARTICIPANTS] = _struct("Participants", [("header", Header), ("num_active_cars", u8),
                                               ("cars", part * n)])

    setup = _struct("Setup", [
        ("front_wing", u8), ("rear_wing", u8), ("on_throttle", u8), ("off_throttle", u8),
        ("front_camber", f32), ("rear_camber", f32), ("front_toe", f32), ("rear_toe", f32),
        ("front_suspension", u8), ("rear_suspension", u8), ("front_anti_roll_bar", u8),
        ("rear_anti_roll_bar", u8), ("front_suspension_height", u8),
        ("rear_suspension_height", u8), ("brake_pressure", u8), ("brake_bias", u8),
        ("engine_braking", u8), ("rear_left_tyre_pressure", f32),
        ("rear_right_tyre_pressure", f32), ("front_left_tyre_pressure", f32),
        ("front_right_tyre_pressure", f32), ("ballast", u8), ("fuel_load", f32)])
    S[SETUPS] = _struct("Setups", [("header", Header), ("cars", setup * n),
                                   ("next_front_wing_value", f32)])

    tele = _struct("Tele", [
        ("speed", u16), ("throttle", f32), ("steer", f32), ("brake", f32), ("clutch", u8),
        ("gear", i8), ("engine_rpm", u16), ("drs", u8), ("rev_lights_percent", u8),
        ("rev_lights_bit_value", u16), ("brakes_temperature", u16 * 4),
        ("tyres_surface_temperature", u8 * 4), ("tyres_inner_temperature", u8 * 4),
        ("engine_temperature", u8 if formato == 2026 else u16), ("tyres_pressure", f32 * 4),
        ("surface_type", u8 * 4)])
    S[TELEMETRY] = _struct("Telemetry", [
        ("header", Header), ("cars", tele * n), ("mfd_panel_index", u8),
        ("mfd_panel_index_secondary_player", u8), ("suggested_gear", i8)])

    stat = [
        ("traction_control", u8), ("anti_lock_brakes", u8), ("fuel_mix", u8),
        ("front_brake_bias", u8), ("pit_limiter_status", u8), ("fuel_in_tank", f32),
        ("fuel_capacity", f32), ("fuel_remaining_laps", f32), ("max_rpm", u16),
        ("idle_rpm", u16), ("max_gears", u8), ("drs_allowed", u8),
        ("drs_activation_distance", u16), ("actual_tyre_compound", u8),
        ("visual_tyre_compound", u8), ("tyres_age_laps", u8), ("vehicle_fia_flags", i8),
        ("engine_power_ice", f32), ("engine_power_mguk", f32), ("ers_store_energy", f32),
        ("ers_deploy_mode", u8), ("ers_harvested_this_lap_mguk", f32),
        ("ers_harvested_this_lap_mguh", f32)]
    if formato == 2026:
        stat.append(("ers_harvest_limit_per_lap", f32))
    stat += [("ers_deployed_this_lap", f32), ("network_paused", u8)]
    S[STATUS] = _struct("Status", [("header", Header), ("cars", _struct("Stat", stat) * n)])

    fin = _struct("Fin", [
        ("position", u8), ("num_laps", u8), ("grid_position", u8), ("points", u8),
        ("num_pit_stops", u8), ("result_status", u8), ("result_reason", u8),
        ("best_lap_time_in_ms", u32), ("total_race_time", f64), ("penalties_time", u8),
        ("num_penalties", u8), ("num_tyre_stints", u8), ("tyre_stints_actual", u8 * 8),
        ("tyre_stints_visual", u8 * 8), ("tyre_stints_end_laps", u8 * 8)])
    S[FINAL] = _struct("Final", [("header", Header), ("num_cars", u8), ("cars", fin * n)])

    lobby = _struct("LobbyP", [
        ("ai_controlled", u8), ("team_id", idt), ("nationality", u8), ("platform", u8),
        ("name", ctypes.c_char * 32), ("car_number", u8), ("your_telemetry", u8),
        ("show_online_names", u8), ("tech_level", u16), ("ready_status", u8)])
    S[LOBBY] = _struct("Lobby", [("header", Header), ("num_players", u8), ("cars", lobby * n)])

    dmg = _struct("Dmg", [
        ("tyres_wear", f32 * 4), ("tyres_damage", u8 * 4), ("brakes_damage", u8 * 4),
        ("tyre_blisters", u8 * 4), ("front_left_wing_damage", u8),
        ("front_right_wing_damage", u8), ("rear_wing_damage", u8), ("floor_damage", u8),
        ("diffuser_damage", u8), ("sidepod_damage", u8), ("drs_fault", u8), ("ers_fault", u8),
        ("gear_box_damage", u8), ("engine_damage", u8), ("engine_mguh_wear", u8),
        ("engine_es_wear", u8), ("engine_ce_wear", u8), ("engine_ice_wear", u8),
        ("engine_mguk_wear", u8), ("engine_tc_wear", u8), ("engine_blown", u8),
        ("engine_seized", u8)])
    S[DAMAGE] = _struct("Damage", [("header", Header), ("cars", dmg * n)])

    giro = _struct("Giro", [
        ("lap_time_in_ms", u32), ("sector1_time_ms_part", u16), ("sector1_time_minutes_part", u8),
        ("sector2_time_ms_part", u16), ("sector2_time_minutes_part", u8),
        ("sector3_time_ms_part", u16), ("sector3_time_minutes_part", u8),
        ("lap_valid_bit_flags", u8)])
    stint = _struct("Stint", [("end_lap", u8), ("tyre_actual_compound", u8),
                              ("tyre_visual_compound", u8)])
    S[HISTORY] = _struct("History", [
        ("header", Header), ("car_idx", u8), ("num_laps", u8), ("num_tyre_stints", u8),
        ("best_lap_time_lap_num", u8), ("best_sector1_lap_num", u8),
        ("best_sector2_lap_num", u8), ("best_sector3_lap_num", u8),
        ("laps", giro * 100), ("stints", stint * 8)])

    tset = _struct("TSet", [
        ("actual_tyre_compound", u8), ("visual_tyre_compound", u8), ("wear", u8),
        ("available", u8), ("recommended_session", u8), ("life_span", u8),
        ("usable_life", u8), ("lap_delta_time", i16), ("fitted", u8)])
    S[TYRESETS] = _struct("TyreSets", [("header", Header), ("car_idx", u8),
                                       ("sets", tset * 20), ("fitted_idx", u8)])

    f4 = f32 * 4
    S[MOTIONEX] = _struct("MotionEx", [
        ("header", Header), ("suspension_position", f4), ("suspension_velocity", f4),
        ("suspension_acceleration", f4), ("wheel_speed", f4), ("wheel_slip_ratio", f4),
        ("wheel_slip_angle", f4), ("wheel_lat_force", f4), ("wheel_long_force", f4),
        ("height_of_cog_above_ground", f32), ("local_velocity_x", f32),
        ("local_velocity_y", f32), ("local_velocity_z", f32), ("angular_velocity_x", f32),
        ("angular_velocity_y", f32), ("angular_velocity_z", f32),
        ("angular_acceleration_x", f32), ("angular_acceleration_y", f32),
        ("angular_acceleration_z", f32), ("front_wheels_angle", f32), ("wheel_vert_force", f4),
        ("front_aero_height", f32), ("rear_aero_height", f32), ("front_roll_angle", f32),
        ("rear_roll_angle", f32), ("chassis_yaw", f32), ("chassis_pitch", f32),
        ("wheel_camber", f4), ("wheel_camber_gain", f4)])

    tt = _struct("TT", [
        ("car_idx", u8), ("team_id", idt), ("lap_time_in_ms", u32), ("sector1_time_in_ms", u32),
        ("sector2_time_in_ms", u32), ("sector3_time_in_ms", u32), ("traction_control", u8),
        ("gearbox_assist", u8), ("anti_lock_brakes", u8), ("equal_car_performance", u8),
        ("custom_setup", u8), ("valid", u8)])
    S[TIMETRIAL] = _struct("TimeTrial", [("header", Header), ("player_session_best", tt),
                                         ("personal_best", tt), ("rival", tt)])

    S[LAPPOS] = _struct("LapPos", [("header", Header), ("num_laps", u8), ("lap_start", u8),
                                   ("positions", u8 * (50 * n))])

    if formato == 2026:
        t2 = _struct("Tele2", [
            ("active_aero_mode", u8), ("active_aero_available", u8),
            ("active_aero_activation_distance", u16), ("overtake_available", u8),
            ("overtake_active", u8), ("overtake_activation_distance", u16),
            ("regulations_2026", u8), ("driving_wrong_way", u8)])
        S[TELEMETRY2] = _struct("Telemetry2", [("header", Header), ("cars", t2 * n)])
    S["n"] = n
    return S


STRUTTURE = {f: _definisci(f) for f in FORMATI}


def taglie(formato):
    """{id: byte} per un formato."""
    return {k: ctypes.sizeof(v) for k, v in STRUTTURE[formato].items() if isinstance(k, int)}


TAGLIE = {f: taglie(f) for f in FORMATI}


class Pacchetto:
    """Un pacchetto decodificato: `.id`, `.formato`, `.header`, `.dati` (struttura ctypes)."""
    __slots__ = ("id", "formato", "header", "dati", "nome")

    def __init__(self, pid, formato, header, dati):
        self.id, self.formato, self.header, self.dati = pid, formato, header, dati
        self.nome = NOMI.get(pid, str(pid))


def intestazione(buf):
    if len(buf) < HEADER_SIZE:
        return None
    return Header.from_buffer_copy(buf)


def decodifica(buf, solo=None):
    """Decodifica un datagramma. Restituisce Pacchetto, oppure None se il formato o la
    taglia non tornano (pacchetto scartato). `solo` = insieme di id da decodificare."""
    h = intestazione(buf)
    if h is None or h.packet_format not in STRUTTURE:
        return None
    pid = h.packet_id
    S = STRUTTURE[h.packet_format]
    cls = S.get(pid)
    if cls is None:
        return None
    if solo is not None and pid not in solo:
        return Pacchetto(pid, h.packet_format, h, None)
    size = ctypes.sizeof(cls)
    if len(buf) < size:
        return None
    return Pacchetto(pid, h.packet_format, h, cls.from_buffer_copy(buf[:size]))


def codice_evento(p):
    return bytes(p.dati.code).decode("ascii", "replace")


# ---- enum utili (dalla specifica) ----
GOMME_VISIVE = {16: "soft", 17: "medium", 18: "hard", 7: "intermedie", 8: "da bagnato",
                15: "da bagnato", 19: "super soft", 20: "soft", 21: "hard", 22: "soft",
                23: "medium", 24: "hard"}
GOMME_SLICK = {16, 17, 18, 19, 20, 21, 22, 23, 24}
METEO = {0: "sereno", 1: "poco nuvoloso", 2: "nuvoloso", 3: "pioggia leggera",
         4: "pioggia forte", 5: "temporale"}
# tipi di sessione (F1 24/25): 15-17 gara, 10-14 sprint shootout, 5-9 qualifica
SESSIONE_GARA = {15, 16, 17}
SESSIONE_QUALIFICA = set(range(5, 15))
SESSIONE_PROVE = {1, 2, 3, 4}
SESSIONE_TIME_TRIAL = 18
NOMI_SESSIONE = {0: "sessione", 1: "prove libere 1", 2: "prove libere 2", 3: "prove libere 3",
                 4: "prove libere corte", 5: "Q1", 6: "Q2", 7: "Q3", 8: "qualifica corta",
                 9: "qualifica su un giro", 10: "sprint shootout 1", 11: "sprint shootout 2",
                 12: "sprint shootout 3", 13: "sprint shootout corto",
                 14: "sprint shootout su un giro", 15: "gara", 16: "gara 2", 17: "gara 3",
                 18: "time trial"}
# ruote: 0 posteriore sinistra, 1 posteriore destra, 2 anteriore sinistra, 3 anteriore destra
RUOTE = ("posteriore sinistra", "posteriore destra", "anteriore sinistra", "anteriore destra")
PISTE = {0: "Melbourne", 2: "Shanghai", 3: "Sakhir", 4: "Barcellona", 5: "Monaco",
         6: "Montréal", 7: "Silverstone", 9: "Hungaroring", 10: "Spa", 11: "Monza",
         12: "Singapore", 13: "Suzuka", 14: "Abu Dhabi", 15: "Austin", 16: "Interlagos",
         17: "Spielberg", 19: "Città del Messico", 20: "Baku", 26: "Zandvoort", 27: "Imola",
         29: "Jeddah", 30: "Miami", 31: "Las Vegas", 32: "Losail", 39: "Silverstone inversa",
         40: "Spielberg inversa", 41: "Zandvoort inversa", 42: "Madrid"}
