# products-backend/ramos/api/services/commission_service.py
from django.db import connection


def get_commission_cap(ramo_ids, modalidad_id=None):
    query = """
    WITH per_node AS (
      SELECT
        n.id AS node_id,
        n.code,
        n.name,
        MIN(CASE
              WHEN cr.rule_type = 'FIXED_PERCENT' THEN (cr.rule_value ->> 'percent')::numeric
              ELSE NULL
            END) AS commission_percent
      FROM ramo.node n
      LEFT JOIN ramo.commission_rule cr
             ON cr.node_id = n.id
            AND (cr.modalidad_id IS NULL OR cr.modalidad_id = COALESCE(:modalidad_id, cr.modalidad_id))
      WHERE n.id = ANY (:ramo_ids)
      GROUP BY n.id, n.code, n.name
    ),
    with_rule AS (
      SELECT * FROM per_node WHERE commission_percent IS NOT NULL
    ),
    no_rule AS (
      SELECT * FROM per_node WHERE commission_percent IS NULL
    )
    SELECT
      (SELECT MIN(commission_percent) FROM with_rule) AS commission_cap_percent,
      jsonb_agg(to_jsonb(wr) ORDER BY wr.name) AS per_ramo_detail,
      jsonb_agg(to_jsonb(nr) ORDER BY nr.name) FILTER (WHERE EXISTS (SELECT 1 FROM no_rule nr2)) AS without_rule
    FROM with_rule wr
    LEFT JOIN no_rule nr ON FALSE;
    """
    params = {'ramo_ids': ramo_ids, 'modalidad_id': modalidad_id}

    with connection.cursor() as cursor:
        cursor.execute(query, params)
        rows = cursor.fetchall()

    return {
        "commission_cap_percent": rows[0][0],
        "per_ramo_detail": rows[0][1],
        "without_rule": rows[0][2],
    }
