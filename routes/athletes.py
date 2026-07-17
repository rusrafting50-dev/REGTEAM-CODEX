# routes/athletes.py — CRUD спортсменов
import re
from datetime import date, datetime

from flask import Blueprint, flash, redirect, render_template, request, url_for

import references
from models import (
    AnthropometryRecord,
    Athlete,
    Award,
    ChangeLog,
    CompetitionParticipation,
    GtoRecord,
    MedicalClearance,
    NormFulfillment,
    Penalty,
    TransferRecord,
    YearlySummary,
    db,
)

bp = Blueprint("athletes", __name__, url_prefix="/athletes")

PER_PAGE = 20

# Маршрут (Маршрут - лыжный, водный, горный и т.д. "N-N категория") — независимо от пробелов/дефиса
ROUTE_DISCIPLINE_PATTERN = r"\(\s*\d+\s*-\s*\d+\s*категория\s*\)"

# Дистанции / Дистанция / Группа дисциплин "дистанция" — без учёта регистра
DISTANCE_DISCIPLINE_PATTERN = r"(?i)дистанц"

# Группы вариантов дисциплины для выпадающего списка в форме добавления,
# когда переход выполнен со страницы конкретного типа дистанции/маршрута
DISCIPLINE_OPTION_GROUPS = {
    "hiking-distance": ["Дистанции пешеходные", "Дистанции пешеходные, дистанции лыжные"],
    "ski-distance": ["Дистанции лыжные", "Дистанции пешеходные, дистанции лыжные"],
    "water-distance": ["Дистанции водные", "Дистанции водные, маршрут – водный (1-6 категория)"],
    "water-route": ["Маршрут – водный (1-6 категория)", "Дистанции водные, маршрут – водный (1-6 категория)"],
    "mountain-distance": ["Дистанции горные", "Дистанции горные, маршрут – горный (1-6 категория)"],
    "mountain-route": ["Маршрут – горный (1-6 категория)", "Дистанции горные, маршрут – горный (1-6 категория)"],
    "vehicle-distance": ["Дистанции на средствах передвижения", "Дистанции на средствах передвижения, маршрут – на средствах передвижения (1-6 категория)"],
    "vehicle-route": ["Маршрут – на средствах передвижения (1-6 категория)", "Дистанции на средствах передвижения, маршрут – на средствах передвижения (1-6 категория)"],
}

# Конкретные виды маршрутов для кнопок на странице /athletes/routes:
# (путь, подпись кнопки, эндпоинт, паттерн дисциплины, заголовок страницы, дисциплина для предзаполнения при добавлении, скрыть фильтр "Дисциплина", группа вариантов дисциплины)
ROUTE_TYPES = [
    ("/routes/ski", "Маршрут - лыжный (1 - 6 категория)", "athletes.athletes_routes_ski", r"(?is)маршрут.*лыжн.*\(\s*\d+\s*-\s*\d+\s*категория\s*\)", "Маршрут - лыжный (1-6 категория)", "Маршрут - лыжный (1-6 категория)", True, None),
    ("/routes/hiking", "Маршрут - пешеходный (1 - 6 категория)", "athletes.athletes_routes_hiking", r"(?is)маршрут.*пешеход.*\(\s*\d+\s*-\s*\d+\s*категория\s*\)", "Маршрут - пешеходный (1-6 категория)", "Маршрут - пешеходный (1-6 категория)", True, None),
    ("/routes/mountain", "Маршрут - горный (1 - 6 категория)", "athletes.athletes_routes_mountain", r"(?is)маршрут.*горн.*\(\s*\d+\s*-\s*\d+\s*категория\s*\)", "Маршрут - горный (1-6 категория)", "Маршрут - горный (1-6 категория)", True, "mountain-route"),
    ("/routes/water", "Маршрут - водный (1 - 6 категория)", "athletes.athletes_routes_water", r"(?is)маршрут.*водн.*\(\s*\d+\s*-\s*\d+\s*категория\s*\)", None, None, True, "water-route"),
    ("/routes/vehicle", "Маршрут – на средствах передвижения (1 - 6 категория)", "athletes.athletes_routes_vehicle", r"(?is)маршрут.*средствах передвижения.*\(\s*\d+\s*-\s*\d+\s*категория\s*\)", "Маршрут - на средствах передвижения (1-6 категория)", "Маршрут - на средствах передвижения (1-6 категория)", True, "vehicle-route"),
]

# Тренер / Главный тренер / тренер — без учёта регистра
TRAINER_CATEGORY_PATTERN = r"(?i)тренер"

# Варианты дисциплины для формы добавления тренера
TRAINER_DISCIPLINE_OPTIONS = [
    'Группа дисциплин «дистанция»',
    "Дистанции пешеходные",
    "Дистанции лыжные",
    "Дистанции пешеходные, дистанции лыжные",
    "Дистанции горные",
    "Дистанции спелео",
    "Дистанции водные",
    "Дистанции на средствах передвижения",
    'Группа дисциплин «маршрут»',
    "Маршрут - пешеходный (1-6 категория)",
    "Маршрут - лыжный (1-6 категория)",
    "Маршрут - горный (1-6 категория)",
    "Маршрут - водный (1-6 категория)",
    "Маршрут – на средствах передвижения (1-6 категория)",
]

# Варианты категории для формы добавления тренера
TRAINER_CATEGORY_OPTIONS = ["Главный тренер", "Тренер", "Специалист"]

# Категория для формы добавления спортсмена
ATHLETE_CATEGORY_OPTIONS = ["Спортсмен"]

# Варианты возрастной категории для формы добавления тренера
TRAINER_AGE_CATEGORY_OPTIONS = [
    "Все возрастные категории",
    "Мужчины",
    "Женщины",
    "Мужчины, женщины",
    "Юниоры",
    "Юниорки",
    "Юниоры, юниорки",
    "Юноши",
    "Девушки",
    "Юноши, девушки",
]

# Конкретные виды дистанций для кнопок на странице /athletes/distances:
# (путь, подпись кнопки, эндпоинт, паттерн дисциплины, заголовок страницы, дисциплина для предзаполнения при добавлении, скрыть фильтр "Дисциплина", группа вариантов дисциплины)
DISTANCE_TYPES = [
    ("/distances/hiking", "Дистанции пешеходные", "athletes.athletes_distances_hiking", r"(?is)дистанц.*пешеход", "Дистанции пешеходные", "Дистанции пешеходные", True, "hiking-distance"),
    ("/distances/ski", "Дистанции лыжные", "athletes.athletes_distances_ski", r"(?is)дистанц.*лыжн", "Дистанции лыжные", "Дистанции лыжные", True, "ski-distance"),
    ("/distances/mountain", "Дистанции горные", "athletes.athletes_distances_mountain", r"(?is)дистанц.*горн", "Дистанции горные", "Дистанции горные", True, "mountain-distance"),
    ("/distances/speleo", "Дистанции спелео", "athletes.athletes_distances_speleo", r"(?is)дистанц.*спелео", "Дистанции спелео", "Дистанции спелео", True, None),
    ("/distances/water", "Дистанции водные", "athletes.athletes_distances_water", r"(?is)дистанц.*водн", "Дистанции водные", "Дистанции водные", True, "water-distance"),
    ("/distances/vehicle", "Дистанции на средствах передвижения", "athletes.athletes_distances_vehicle", r"(?is)дистанц.*средствах передвижения", "Дистанции на средствах передвижения", "Дистанции на средствах передвижения", True, "vehicle-distance"),
]


def _apply_common_filters(query):
    discipline = request.args.get("discipline", "")
    age_category = request.args.get("age_category", "")
    territory = request.args.get("territory", "")
    organization = request.args.get("organization", "")

    if discipline:
        query = query.filter(Athlete.discipline.contains(discipline))
    if age_category:
        query = query.filter(Athlete.age_category == age_category)
    if territory:
        query = query.filter(Athlete.territory == territory)
    if organization:
        query = query.filter(Athlete.organization == organization)

    filters = {
        "discipline": discipline,
        "age_category": age_category,
        "territory": territory,
        "organization": organization,
    }
    return query, filters


def _with_current_value(options, current_value):
    """Список options, дополненный current_value, если его там ещё нет (чтобы не потерять при сохранении)."""
    if current_value and current_value not in options:
        return options + [current_value]
    return options


def _merge_discipline_family(distance_group, route_group):
    """Объединяет варианты дистанции и маршрута одного вида (напр. водный) для формы редактирования."""
    pure_distance, combined = DISCIPLINE_OPTION_GROUPS[distance_group]
    pure_route, _ = DISCIPLINE_OPTION_GROUPS[route_group]
    return [pure_distance, pure_route, combined]


# Варианты дисциплины для формы редактирования спортсмена — объединяют выпадающие
# списки страниц "Добавление спортсмена" для дистанции и маршрута одного вида,
# чтобы при редактировании ничего не терялось независимо от того, откуда перешли.
DISCIPLINE_EDIT_FAMILIES = [
    _merge_discipline_family("hiking-distance", "ski-distance"),
    _merge_discipline_family("water-distance", "water-route"),
    _merge_discipline_family("mountain-distance", "mountain-route"),
    _merge_discipline_family("vehicle-distance", "vehicle-route"),
]


def _discipline_family_options(discipline):
    for family in DISCIPLINE_EDIT_FAMILIES:
        if discipline in family:
            return family
    return None


def _distinct_organizations():
    rows = (
        db.session.query(Athlete.organization)
        .filter(Athlete.organization.isnot(None), Athlete.organization != "")
        .distinct()
        .order_by(Athlete.organization)
        .all()
    )
    return [row[0] for row in rows]


def _render_athletes_list(
    query, heading="Спортсмены", show_add_button=True, discipline_preset=None,
    hide_discipline_filter=False, link_fio_to_new=False, link_fio_to_edit=False, discipline_group=None,
    add_button_label="Добавить спортсмена", add_form_variant=None, age_category_filter_options=None,
    highlight_active=True, **extra_context,
):
    query, filters = _apply_common_filters(query)
    page = request.args.get("page", 1, type=int)
    pagination = query.order_by(Athlete.last_name).paginate(page=page, per_page=PER_PAGE, error_out=False)
    return render_template(
        "athletes/list.html",
        athletes=pagination.items,
        pagination=pagination,
        filters=filters,
        references=references,
        organizations=_distinct_organizations(),
        heading=heading,
        show_add_button=show_add_button,
        discipline_preset=discipline_preset,
        hide_discipline_filter=hide_discipline_filter,
        link_fio_to_new=link_fio_to_new,
        link_fio_to_edit=link_fio_to_edit,
        age_category_filter_options=age_category_filter_options or references.AGE_CATEGORIES,
        discipline_group=discipline_group,
        add_button_label=add_button_label,
        add_form_variant=add_form_variant,
        highlight_active=highlight_active,
        **extra_context,
    )


@bp.route("/")
def athletes_list():
    query = Athlete.query.filter_by(is_active=True)
    return _render_athletes_list(
        query, heading="Список сборной команды",
        show_add_button=False, highlight_active=False,
    )


@bp.route("/routes")
def athletes_routes_list():
    query = Athlete.query.filter(
        Athlete.discipline.op("REGEXP")(ROUTE_DISCIPLINE_PATTERN)
    )
    return _render_athletes_list(
        query, list_buttons=ROUTE_TYPES,
        heading="Группа дисциплин МАРШРУТ", show_add_button=False,
    )


@bp.route("/trainers")
def athletes_trainers_list():
    query = Athlete.query.filter(
        Athlete.category.op("REGEXP")(TRAINER_CATEGORY_PATTERN)
    )
    return _render_athletes_list(
        query, heading="Тренеры",
        add_button_label="Добавить тренера", add_form_variant="trainer",
        age_category_filter_options=TRAINER_AGE_CATEGORY_OPTIONS,
    )


@bp.route("/distances")
def athletes_distances_list():
    query = Athlete.query.filter(
        Athlete.discipline.op("REGEXP")(DISTANCE_DISCIPLINE_PATTERN)
    )
    return _render_athletes_list(
        query, list_buttons=DISTANCE_TYPES,
        heading="Группа дисциплин ДИСТАНЦИЯ", show_add_button=False,
    )


def _make_discipline_type_view(pattern, heading, discipline_preset, hide_discipline_filter, discipline_group):
    def view():
        query = Athlete.query.filter(
            Athlete.discipline.op("REGEXP")(pattern)
        )
        kwargs = {"hide_discipline_filter": hide_discipline_filter}
        if heading:
            kwargs["heading"] = heading
        if discipline_preset:
            kwargs["discipline_preset"] = discipline_preset
        if discipline_group:
            kwargs["discipline_group"] = discipline_group
        return _render_athletes_list(query, **kwargs)
    return view


for _path, _label, _endpoint, _pattern, _heading, _discipline_preset, _hide_discipline_filter, _discipline_group in ROUTE_TYPES + DISTANCE_TYPES:
    bp.add_url_rule(
        _path,
        endpoint=_endpoint.split(".")[1],
        view_func=_make_discipline_type_view(_pattern, _heading, _discipline_preset, _hide_discipline_filter, _discipline_group),
    )


@bp.route("/new", methods=["GET", "POST"])
def athletes_new():
    if request.method == "POST":
        athlete = Athlete()
        _fill_athlete_from_form(athlete, request.form)
        db.session.add(athlete)
        db.session.commit()
        flash("Спортсмен добавлен", "success")
        return redirect(url_for("athletes.athletes_detail", athlete_id=athlete.id))

    if request.args.get("form_variant") == "trainer":
        discipline_options = TRAINER_DISCIPLINE_OPTIONS
        category_options = TRAINER_CATEGORY_OPTIONS
        age_category_options = TRAINER_AGE_CATEGORY_OPTIONS
        entity_label = "тренера"
    else:
        discipline_options = DISCIPLINE_OPTION_GROUPS.get(request.args.get("discipline_group", ""))
        category_options = ATHLETE_CATEGORY_OPTIONS
        age_category_options = None
        entity_label = "спортсмена"

    preset_discipline = request.args.get("discipline", "")
    if discipline_options and not preset_discipline:
        preset_discipline = discipline_options[0]

    return render_template(
        "athletes/form.html", athlete=None, references=references,
        preset_discipline=preset_discipline, discipline_options=discipline_options,
        category_options=category_options, age_category_options=age_category_options,
        entity_label=entity_label,
    )


@bp.route("/<int:athlete_id>")
def athletes_detail(athlete_id):
    athlete = Athlete.query.get_or_404(athlete_id)

    records_by_cell = {(r.metric, r.column_index): r for r in athlete.anthropometry_records}
    anthropometry_headers = [""] * 5
    for r in athlete.anthropometry_records:
        if r.year_label and 1 <= r.column_index <= 5:
            anthropometry_headers[r.column_index - 1] = r.year_label
    anthropometry_rows = []
    for i, metric in enumerate(references.ANTHROPOMETRY_METRICS):
        values = [
            (records_by_cell[(metric, col)].value or "") if (metric, col) in records_by_cell else ""
            for col in range(1, 6)
        ]
        anthropometry_rows.append((i, metric, values))

    return render_template(
        "athletes/detail.html", athlete=athlete, references=references,
        anthropometry_headers=anthropometry_headers, anthropometry_rows=anthropometry_rows,
    )


@bp.route("/<int:athlete_id>/edit", methods=["GET", "POST"])
def athletes_edit(athlete_id):
    athlete = Athlete.query.get_or_404(athlete_id)

    if request.method == "POST":
        _fill_athlete_from_form(athlete, request.form)
        db.session.commit()
        flash("Изменения сохранены", "success")
        return redirect(url_for("athletes.athletes_detail", athlete_id=athlete.id))

    is_trainer = bool(athlete.category and re.search(TRAINER_CATEGORY_PATTERN, athlete.category))
    if is_trainer:
        # Текущее значение спортсмена может не совпадать буквально ни с одним
        # из готовых вариантов (регистр, кавычки и т.п.) — добавляем его в список,
        # чтобы оно корректно подставлялось и не терялось при сохранении без изменений.
        category_options = _with_current_value(TRAINER_CATEGORY_OPTIONS, athlete.category)
        age_category_options = _with_current_value(TRAINER_AGE_CATEGORY_OPTIONS, athlete.age_category)
        discipline_options = _with_current_value(TRAINER_DISCIPLINE_OPTIONS, athlete.discipline)
        entity_label = "тренера"
    else:
        category_options = None
        age_category_options = None
        discipline_options = _discipline_family_options(athlete.discipline)
        entity_label = "спортсмена"

    return render_template(
        "athletes/form.html", athlete=athlete, references=references,
        category_options=category_options, age_category_options=age_category_options,
        discipline_options=discipline_options, entity_label=entity_label,
    )


@bp.route("/<int:athlete_id>/deactivate", methods=["POST"])
def athletes_deactivate(athlete_id):
    athlete = Athlete.query.get_or_404(athlete_id)
    athlete.is_active = False
    db.session.add(
        ChangeLog(athlete_id=athlete.id, change_type="исключён", change_date=date.today())
    )
    db.session.commit()
    flash("Спортсмен исключён из списка", "success")
    return redirect(url_for("athletes.athletes_detail", athlete_id=athlete.id))


@bp.route("/<int:athlete_id>/activate", methods=["POST"])
def athletes_activate(athlete_id):
    athlete = Athlete.query.get_or_404(athlete_id)
    is_first_add = not athlete.change_logs
    athlete.is_active = True
    db.session.add(
        ChangeLog(athlete_id=athlete.id, change_type="включён", change_date=date.today())
    )
    db.session.commit()
    flash("Спортсмен добавлен в список" if is_first_add else "Спортсмен возвращён в список", "success")
    return redirect(url_for("athletes.athletes_detail", athlete_id=athlete.id))


@bp.route("/<int:athlete_id>/delete", methods=["POST"])
def athletes_delete(athlete_id):
    athlete = Athlete.query.get_or_404(athlete_id)
    is_trainer = bool(athlete.category and re.search(TRAINER_CATEGORY_PATTERN, athlete.category))
    db.session.delete(athlete)
    db.session.commit()
    flash("Тренер удалён" if is_trainer else "Спортсмен удалён", "success")
    return redirect(url_for("athletes.athletes_trainers_list" if is_trainer else "athletes.athletes_list"))


@bp.route("/change-logs/<int:log_id>/edit", methods=["POST"])
def change_log_edit(log_id):
    log = ChangeLog.query.get_or_404(log_id)
    date_raw = request.form.get("change_date", "").strip()
    if date_raw:
        try:
            log.change_date = datetime.strptime(date_raw, "%Y-%m-%d").date()
        except ValueError:
            flash("Некорректная дата", "error")
            return redirect(url_for("athletes.athletes_detail", athlete_id=log.athlete_id))
    log.document_number = request.form.get("document_number", "").strip() or None
    db.session.commit()
    flash("Запись о членстве в сборной команде обновлена", "success")
    return redirect(url_for("athletes.athletes_detail", athlete_id=log.athlete_id))


@bp.route("/change-logs/<int:log_id>/delete", methods=["POST"])
def change_log_delete(log_id):
    log = ChangeLog.query.get_or_404(log_id)
    athlete_id = log.athlete_id
    db.session.delete(log)
    db.session.commit()
    flash("Запись о членстве в сборной команде удалена", "success")
    return redirect(url_for("athletes.athletes_detail", athlete_id=athlete_id))


def _register_athlete_subtable_routes(model, slug, field_types, label):
    """Регистрирует POST-маршруты добавления/изменения/удаления записи простой
    CRUD-таблицы раздела разрядной книжки (одинаковой структуры для разных разделов)."""

    def _apply_fields(record, form):
        for name, kind in field_types.items():
            raw = form.get(name, "").strip()
            if kind == "date":
                setattr(record, name, datetime.strptime(raw, "%Y-%m-%d").date() if raw else None)
            else:
                setattr(record, name, raw or None)

    def add_view(athlete_id):
        athlete = Athlete.query.get_or_404(athlete_id)
        record = model(athlete_id=athlete.id)
        _apply_fields(record, request.form)
        db.session.add(record)
        db.session.commit()
        flash(f"{label}: запись добавлена", "success")
        return redirect(url_for("athletes.athletes_detail", athlete_id=athlete.id))

    def edit_view(record_id):
        record = model.query.get_or_404(record_id)
        _apply_fields(record, request.form)
        db.session.commit()
        flash(f"{label}: запись обновлена", "success")
        return redirect(url_for("athletes.athletes_detail", athlete_id=record.athlete_id))

    def delete_view(record_id):
        record = model.query.get_or_404(record_id)
        athlete_id = record.athlete_id
        db.session.delete(record)
        db.session.commit()
        flash(f"{label}: запись удалена", "success")
        return redirect(url_for("athletes.athletes_detail", athlete_id=athlete_id))

    bp.add_url_rule(f"/<int:athlete_id>/{slug}", endpoint=f"{slug}_add", view_func=add_view, methods=["POST"])
    bp.add_url_rule(f"/{slug}/<int:record_id>/edit", endpoint=f"{slug}_edit", view_func=edit_view, methods=["POST"])
    bp.add_url_rule(f"/{slug}/<int:record_id>/delete", endpoint=f"{slug}_delete", view_func=delete_view, methods=["POST"])


_register_athlete_subtable_routes(
    MedicalClearance, "medical_clearances",
    {"date": "date", "valid_until": "date", "doctor_name": "text"},
    "Разрешение врача",
)
_register_athlete_subtable_routes(
    TransferRecord, "transfer_records",
    {"left_organization": "text", "joined_organization": "text"},
    "Отметка о переходе",
)
_register_athlete_subtable_routes(
    Penalty, "penalties",
    {"date": "date", "description": "text", "responsible_person": "text"},
    "Взыскание",
)
_register_athlete_subtable_routes(
    GtoRecord, "gto_records",
    {"date": "date", "result": "text", "responsible_person": "text"},
    "Сдача норм ГТО",
)
_register_athlete_subtable_routes(
    NormFulfillment, "norm_fulfillments",
    {"requirement_level": "text", "date": "date", "result": "text", "responsible_person": "text"},
    "Выполнение норм",
)
_register_athlete_subtable_routes(
    YearlySummary, "yearly_summaries",
    {"year": "text", "competitions_count": "text", "best_result": "text"},
    "Итоговые данные об участии в соревнованиях",
)
_register_athlete_subtable_routes(
    Award, "awards",
    {"date": "date", "reason": "text", "awarded_by": "text"},
    "Награждение",
)
_register_athlete_subtable_routes(
    CompetitionParticipation, "competition_participations",
    {"date": "date", "competition_name": "text", "result": "text", "responsible_person": "text"},
    "Данные об участии в соревнованиях",
)


@bp.route("/<int:athlete_id>/anthropometry", methods=["POST"])
def anthropometry_save(athlete_id):
    athlete = Athlete.query.get_or_404(athlete_id)
    AnthropometryRecord.query.filter_by(athlete_id=athlete.id).delete()
    headers = [request.form.get(f"header_{col}", "").strip() for col in range(1, 6)]
    for i, metric in enumerate(references.ANTHROPOMETRY_METRICS):
        for col in range(1, 6):
            value = request.form.get(f"value_{i}_{col}", "").strip()
            db.session.add(AnthropometryRecord(
                athlete_id=athlete.id, metric=metric, column_index=col,
                year_label=headers[col - 1] or None, value=value or None,
            ))
    athlete.doctor_notes = request.form.get("doctor_notes", "").strip() or None
    db.session.commit()
    flash("Антропометрические данные сохранены", "success")
    return redirect(url_for("athletes.athletes_detail", athlete_id=athlete.id))


def _fill_athlete_from_form(athlete, form):
    athlete.last_name = form.get("last_name", "").strip()
    athlete.first_name = form.get("first_name", "").strip()
    athlete.middle_name = form.get("middle_name", "").strip() or None

    birth_date = form.get("birth_date", "")
    athlete.birth_date = datetime.strptime(birth_date, "%Y-%m-%d").date() if birth_date else None

    athlete.gender = form.get("gender", "")
    athlete.discipline = form.get("discipline", "")
    athlete.category = form.get("category", "")
    athlete.age_category = form.get("age_category", "")
    athlete.rank = form.get("rank", "")
    athlete.organization = form.get("organization", "").strip()
    athlete.territory = form.get("territory", "")
    athlete.trainer = form.get("trainer", "").strip()
    athlete.workplace = form.get("workplace", "").strip()
    athlete.result_regional = form.get("result_regional", "").strip()
    athlete.result_national = form.get("result_national", "").strip()
    athlete.result_international = form.get("result_international", "").strip()
    athlete.national_team = form.get("national_team", "").strip()
