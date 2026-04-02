from skywatch_mcp.lib.sql_validation import validate_query, ValidationSuccess, ValidationFailure


class TestRejectNonSelectStatements:
    """Reject non-SELECT statements"""

    def test_should_reject_insert_statements(self):
        result = validate_query("INSERT INTO osprey_execution_results (id) VALUES (1)")
        assert isinstance(result, ValidationFailure)
        assert "Only SELECT queries are allowed" in result.reason

    def test_should_reject_update_statements(self):
        result = validate_query("UPDATE osprey_execution_results SET id = 1 LIMIT 10")
        assert isinstance(result, ValidationFailure)
        assert "Only SELECT queries are allowed" in result.reason

    def test_should_reject_delete_statements(self):
        result = validate_query("DELETE FROM osprey_execution_results LIMIT 10")
        assert isinstance(result, ValidationFailure)
        assert "Only SELECT queries are allowed" in result.reason

    def test_should_reject_drop_statements(self):
        result = validate_query("DROP TABLE osprey_execution_results")
        assert isinstance(result, ValidationFailure)
        assert "Only SELECT queries are allowed" in result.reason

    def test_should_reject_alter_statements(self):
        result = validate_query("ALTER TABLE osprey_execution_results ADD COLUMN foo INT")
        assert isinstance(result, ValidationFailure)
        assert "Only SELECT queries are allowed" in result.reason

    def test_should_reject_create_statements(self):
        result = validate_query("CREATE TABLE osprey_execution_results (id INT)")
        assert isinstance(result, ValidationFailure)
        assert "Only SELECT queries are allowed" in result.reason

    def test_should_reject_truncate_statements(self):
        result = validate_query("TRUNCATE TABLE osprey_execution_results")
        assert isinstance(result, ValidationFailure)
        assert "Only SELECT queries are allowed" in result.reason


class TestRequireLimitClause:
    """Require LIMIT clause"""

    def test_should_reject_select_without_limit(self):
        result = validate_query("SELECT * FROM osprey_execution_results")
        assert isinstance(result, ValidationFailure)
        assert "LIMIT" in result.reason

    def test_should_reject_select_with_limit_but_no_numeric_value(self):
        result = validate_query("SELECT * FROM osprey_execution_results LIMIT")
        assert isinstance(result, ValidationFailure)
        assert "LIMIT" in result.reason

    def test_should_accept_select_with_valid_limit_clause(self):
        result = validate_query("SELECT * FROM osprey_execution_results LIMIT 10")
        assert isinstance(result, ValidationSuccess)

    def test_should_accept_select_with_large_limit_value(self):
        result = validate_query("SELECT * FROM osprey_execution_results LIMIT 999999")
        assert isinstance(result, ValidationSuccess)

    def test_should_reject_query_with_limit_but_non_numeric_value(self):
        result = validate_query("SELECT * FROM osprey_execution_results LIMIT foo")
        assert isinstance(result, ValidationFailure)
        assert "LIMIT" in result.reason


class TestAllowJoinsAndUnions:
    """Allow JOINs and UNIONs"""

    def test_should_accept_join_queries(self):
        result = validate_query(
            "SELECT a.* FROM osprey_execution_results a JOIN url_cosharing_clusters b ON a.did = b.did LIMIT 10"
        )
        assert isinstance(result, ValidationSuccess)

    def test_should_accept_left_join_queries(self):
        result = validate_query(
            "SELECT * FROM osprey_execution_results LEFT JOIN url_cosharing_membership ON 1=1 LIMIT 10"
        )
        assert isinstance(result, ValidationSuccess)

    def test_should_accept_union_queries(self):
        result = validate_query(
            "SELECT did FROM osprey_execution_results UNION SELECT did FROM pds_signup_anomalies LIMIT 10"
        )
        assert isinstance(result, ValidationSuccess)

    def test_should_accept_union_all_queries(self):
        result = validate_query(
            "SELECT did FROM osprey_execution_results UNION ALL SELECT did FROM pds_signup_anomalies LIMIT 10"
        )
        assert isinstance(result, ValidationSuccess)


class TestAllowAnyTable:
    """Allow any table"""

    def test_should_accept_queries_targeting_any_table(self):
        result = validate_query("SELECT * FROM some_other_table LIMIT 10")
        assert isinstance(result, ValidationSuccess)

    def test_should_accept_queries_without_from_clause(self):
        result = validate_query("SELECT 1 LIMIT 10")
        assert isinstance(result, ValidationSuccess)

    def test_should_accept_subqueries(self):
        result = validate_query(
            "SELECT * FROM (SELECT did, count() as cnt FROM osprey_execution_results GROUP BY did) LIMIT 10"
        )
        assert isinstance(result, ValidationSuccess)

    def test_should_accept_ctes(self):
        result = validate_query(
            "WITH active AS (SELECT did FROM osprey_execution_results) SELECT * FROM active LIMIT 10"
        )
        assert isinstance(result, ValidationSuccess)


class TestCaseInsensitiveHandling:
    """Case-insensitive handling"""

    def test_should_accept_lowercase_select(self):
        result = validate_query("select * from osprey_execution_results limit 10")
        assert isinstance(result, ValidationSuccess)

    def test_should_accept_mixed_case_select(self):
        result = validate_query("Select * From osprey_execution_results Limit 10")
        assert isinstance(result, ValidationSuccess)


class TestWhitespaceNormalization:
    """Whitespace normalization"""

    def test_should_accept_query_with_extra_spaces(self):
        result = validate_query("SELECT  *  FROM   osprey_execution_results   LIMIT   10")
        assert isinstance(result, ValidationSuccess)

    def test_should_accept_query_with_tabs_and_newlines(self):
        result = validate_query("SELECT\n\t*\n\tFROM\n\tosprey_execution_results\n\tLIMIT\n\t10")
        assert isinstance(result, ValidationSuccess)

    def test_should_return_normalized_query_on_success(self):
        result = validate_query("SELECT  *  FROM   osprey_execution_results   LIMIT   10")
        assert isinstance(result, ValidationSuccess)
        assert result.normalized == "SELECT * FROM osprey_execution_results LIMIT 10"


class TestEdgeCases:
    """Edge cases"""

    def test_should_reject_empty_query(self):
        result = validate_query("")
        assert isinstance(result, ValidationFailure)
        assert "empty" in result.reason

    def test_should_reject_whitespace_only_query(self):
        result = validate_query("   \n\t  ")
        assert isinstance(result, ValidationFailure)

    def test_should_accept_complex_valid_query(self):
        result = validate_query(
            "SELECT col1, col2, COUNT(*) as cnt FROM osprey_execution_results WHERE col1 > 5 GROUP BY col1, col2 LIMIT 100"
        )
        assert isinstance(result, ValidationSuccess)

    def test_should_accept_query_with_comment(self):
        result = validate_query(
            "SELECT * FROM osprey_execution_results LIMIT 10 -- this is a comment"
        )
        assert isinstance(result, ValidationSuccess)


class TestDataExportPrevention:
    """Data export prevention"""

    def test_should_reject_queries_with_semicolon_multi_statement(self):
        result = validate_query("SELECT * FROM osprey_execution_results LIMIT 10; DROP TABLE users")
        assert isinstance(result, ValidationFailure)
        assert "semicolon" in result.reason

    def test_should_reject_queries_with_semicolon_at_end(self):
        result = validate_query("SELECT * FROM osprey_execution_results LIMIT 10;")
        assert isinstance(result, ValidationFailure)
        assert "semicolon" in result.reason

    def test_should_reject_into_outfile_queries(self):
        result = validate_query(
            "SELECT * FROM osprey_execution_results INTO OUTFILE '/tmp/data' LIMIT 10"
        )
        assert isinstance(result, ValidationFailure)
        assert "INTO" in result.reason

    def test_should_reject_into_dumpfile_queries(self):
        result = validate_query(
            "SELECT * FROM osprey_execution_results INTO DUMPFILE '/tmp/data' LIMIT 10"
        )
        assert isinstance(result, ValidationFailure)
        assert "INTO" in result.reason
