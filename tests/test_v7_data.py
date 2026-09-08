import json
import tempfile
import unittest
from pathlib import Path

from coverage import build_coverage
from fixture_store import FixtureStore
from league_catalog import load_league_catalog
from source_adapters import AdapterRegistry, SourceAdapter, canonical_key, normalize_fixture
from team_catalog import Team, TeamCatalog
from shard_store import ShardStore
from riskbudur_import import import_file
from core57 import core57_ids, filter_coverage


class RowsAdapter(SourceAdapter):
    def __init__(self, source_id, priority, rows=None, error=None):
        self.source_id, self.priority = source_id, priority
        self.rows, self.error = rows or [], error
        super().__init__()

    def fetch_fixtures(self, league_id, date_from, date_to):
        if self.error:
            raise RuntimeError(self.error)
        return self.rows


class LeagueCatalogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.leagues = load_league_catalog()

    def test_catalog_is_broad_and_not_legacy_35_or_preliminary_94_limit(self):
        self.assertGreater(len(self.leagues), 94)
        self.assertGreater(len({row["country"] for row in self.leagues}), 50)

    def test_required_lower_leagues_exist(self):
        wanted = {
            ("Türkiye", "1. Lig"), ("Türkiye", "2. Lig"), ("Türkiye", "3. Lig"),
            ("Almanya", "3. Liga"), ("İsveç", "Superettan"),
            ("Danimarka", "1st Division"), ("Norveç", "1. Division"),
            ("Japonya", "J1 League"), ("Japonya", "J2 League"), ("Japonya", "J3 League"),
            ("Güney Kore", "K League 1"), ("Güney Kore", "K League 2"),
            ("Çin", "Chinese Super League"), ("Çin", "China League One"),
        }
        actual = {(row["country"], row["canonical_name"]) for row in self.leagues}
        self.assertTrue(wanted <= actual)

    def test_every_league_has_required_catalog_contract(self):
        for row in self.leagues:
            self.assertTrue(row["league_id"])
            self.assertTrue(row["aliases"])
            self.assertIsInstance(row["source_support"], list)
            self.assertTrue(row["active"] and row["men_professional"])


class TeamCatalogTests(unittest.TestCase):
    def test_persistent_team_catalog_is_unique_and_complete(self):
        payload = json.loads(Path("data/team_catalog.json").read_text(encoding="utf-8"))
        self.assertEqual(payload["team_count"], len(payload["teams"]))
        self.assertEqual(len({team["team_id"] for team in payload["teams"]}), payload["team_count"])
        for team in payload["teams"]:
            self.assertTrue(team["canonical_name"] and team["country"] and team["aliases"] and team["league_ids"])

    def test_aliases_resolve_to_one_team(self):
        catalog = TeamCatalog()
        catalog.add(Team("eng.man-united", "Manchester United", "İngiltere", aliases={"Man Utd", "Manchester U."}))
        self.assertEqual(catalog.resolve("man utd", "İngiltere").team_id, "eng.man-united")
        self.assertEqual(catalog.resolve("Manchester U.", "İngiltere").team_id, "eng.man-united")

    def test_aliases_are_country_scoped(self):
        catalog = TeamCatalog()
        catalog.add(Team("us.united", "United", "ABD"))
        self.assertIsNone(catalog.resolve("United", "İngiltere"))


class FixtureTests(unittest.TestCase):
    def test_null_team_fixture_is_rejected(self):
        self.assertIsNone(normalize_fixture({"date": "2026-09-08", "home": None, "away": "B"}, "x.1", "test"))

    def test_historical_scores_are_integers(self):
        row = normalize_fixture({"date": "2026-09-08", "home": "A", "away": "B", "completed": True,
                                 "ht_home": "1", "ht_away": "0", "ft_home": "2", "ft_away": "1"}, "x.1", "test")
        self.assertEqual((row["ht_home"], row["ht_away"], row["ft_home"], row["ft_away"]), (1, 0, 2, 1))

    def test_duplicate_fixtures_merge_and_fallback_survives(self):
        basic = {"date": "2026-09-08", "home": "Man Utd", "away": "Liverpool", "kickoff": "20:00"}
        detail = {**basic, "referee": "Ref A"}
        failed = RowsAdapter("blocked", 1, error="403")
        registry = AdapterRegistry([failed, RowsAdapter("first", 2, [basic]), RowsAdapter("second", 3, [detail])])
        rows = registry.fixtures("eng.premier-league", "2026-09-08", "2026-09-08")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["referee"], "Ref A")
        self.assertEqual(rows[0]["sources"], ["first", "second"])
        self.assertEqual(failed.health.error_count, 1)
        self.assertEqual(failed.health_dict()["status"], "error")

    def test_wrong_league_cannot_merge(self):
        row = {"date": "2026-09-08", "home": "A", "away": "B"}
        registry = AdapterRegistry([RowsAdapter("one", 1, [row])])
        first = registry.fixtures("eng.premier-league", "", "")[0]
        second = registry.fixtures("eng.championship", "", "")[0]
        self.assertNotEqual(first["league_id"], second["league_id"])

    def test_canonical_key_handles_accents_and_punctuation(self):
        self.assertEqual(canonical_key("Manchester U."), canonical_key("Manchester-U"))


class CoverageAndUiContractTests(unittest.TestCase):
    def test_only_history_and_future_is_ok(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = json.loads(Path("data/league_catalog.json").read_text(encoding="utf-8"))
            source["leagues"] = [source["leagues"][1]]
            league = source["leagues"][0]
            legacy = f"{league['country']} {league['canonical_name']}"
            (root / "league_catalog.json").write_text(json.dumps(source), encoding="utf-8")
            (root / "history_meta.json").write_text(json.dumps({"league_counts": {legacy: 80}}), encoding="utf-8")
            fixtures = [{"league": legacy, "home": f"T{i}", "away": f"T{i+1}"} for i in range(0, 8, 2)]
            (root / "future_fixtures.json").write_text(json.dumps({"matches": fixtures}), encoding="utf-8")
            report = build_coverage(root)
            self.assertEqual(report["leagues"][0]["status"], "OK")
            self.assertEqual(report["leagues"][0]["missing_reasons"], [])

    def test_bulletin_and_radar_have_full_analysis_entry(self):
        html = Path("index.html").read_text(encoding="utf-8")
        self.assertIn("openBulletinMatchByKey", html)
        self.assertIn("runWeeklyRadar", html)
        radar = html[html.find("async function runWeeklyRadar"):]
        self.assertIn("await fetchBulletinDate(radarDate)", radar)
        self.assertIn('new Worker("./radar-worker.js")', html)
        self.assertIn("Tam analiz", html)

    def test_mobile_startup_does_not_load_monolithic_history(self):
        html = Path("index.html").read_text(encoding="utf-8")
        startup = html[html.find("async function loadDefault"):]
        self.assertNotIn('fetch("./data/history_10y.json")', startup)
        self.assertNotIn("localStorage.setItem(\"terskose_matches\"", html)

    def test_iphone_fixture_path_is_sharded_and_indexeddb_backed(self):
        html = Path("index.html").read_text(encoding="utf-8")
        central = html.find('/v7/fixtures?date=')
        legacy_file = html.find('./data/future_fixtures.json', central)
        self.assertGreaterEqual(central, 0)
        self.assertGreater(legacy_file, central)
        self.assertIn('indexedDB.open("terskose-v7",1)', html)
        self.assertLess(Path("data/league_catalog.json").stat().st_size, 1_000_000)


class CentralFixtureStoreTests(unittest.TestCase):
    def test_shard_store_retains_richer_valid_fixture(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = ShardStore(tmp)
            base = {"league_id": "x.1", "season": "2026", "date": "2026-09-08", "home": "A", "away": "B", "sources": ["one"]}
            store.save([{**base, "ht_home": 1, "ht_away": 0}], "history")
            store.save([{**base, "sources": ["two"]}], "history")
            saved = json.loads(next(Path(tmp).rglob("history.json")).read_text(encoding="utf-8"))["matches"][0]
            self.assertEqual(saved["ht_home"], 1)
            self.assertEqual(saved["sources"], ["one", "two"])

    def test_store_canonicalizes_merges_and_builds_teams(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            catalog = json.loads(Path("data/league_catalog.json").read_text(encoding="utf-8"))
            catalog["leagues"] = [row for row in catalog["leagues"] if row["league_id"] == "ingiltere.premier-league"]
            (root / "league_catalog.json").write_text(json.dumps(catalog), encoding="utf-8")
            row = {"date": "2026-09-08", "league": "İngiltere Premier League", "home": "Arsenal", "away": "Chelsea"}
            for name in ("current_fixtures.json", "future_fixtures.json", "bulletin_1y.json"):
                (root / name).write_text(json.dumps({"matches": [row]}), encoding="utf-8")
            store = FixtureStore(root)
            fixtures = store.query("2026-09-08")
            self.assertEqual(len(fixtures), 1)
            self.assertEqual(fixtures[0]["league_id"], "ingiltere.premier-league")
            self.assertEqual(len(fixtures[0]["sources"]), 3)
            self.assertEqual(len(store.teams_for(fixtures)), 2)


class RiskbudurImportTests(unittest.TestCase):
    def test_focused_catalog_has_exactly_57_leagues(self):
        payload = json.loads(Path("data/riskbudur_57_catalog.json").read_text(encoding="utf-8"))
        self.assertEqual(payload["league_count"], 57)
        self.assertEqual(len(payload["leagues"]), 57)

    def test_csv_import_normalizes_scores_and_flags(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "sample.csv"
            path.write_text(
                "Ülke,Lig,Sezon,Tarih,Saat,Hafta,Ev Sahibi,Deplasman,İY S,MS S,İY-MS,+6,KG\n"
                "Türkiye,Süper Lig,2026/2027,08.09.2026,20:00,4,Trabzonspor,Galatasaray,1-0,1-2,1/2,0,Var\n",
                encoding="utf-8",
            )
            result = import_file(path)
            self.assertEqual(result["match_count"], 1)
            row = result["matches"][0]
            self.assertEqual(row["league_id"], "turkiye.super-lig")
            self.assertEqual((row["ht_home"], row["ht_away"], row["ft_home"], row["ft_away"]), (1, 0, 1, 2))
            self.assertEqual(row["ht_ft"], "1/2")
            self.assertFalse(row["six_plus"])
            self.assertTrue(row["btts"])


class Core57RuntimeTests(unittest.TestCase):
    def test_core57_has_exactly_57_unique_league_ids(self):
        ids = core57_ids()
        self.assertEqual(len(ids), 57)

    def test_core57_coverage_filters_154_report(self):
        full = json.loads(Path("data/coverage_report.json").read_text(encoding="utf-8"))
        focused = filter_coverage(full)
        self.assertEqual(focused["summary"]["leagues"], 57)
        self.assertEqual(len(focused["leagues"]), 57)


if __name__ == "__main__":
    unittest.main()
