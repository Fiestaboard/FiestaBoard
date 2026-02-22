"""Tests for MUNI nested line structure."""

import pytest
from src.utils.muni import MuniSource
from src.templates.engine import TemplateEngine


class TestMuniLineNormalization:
    """Test line code normalization."""
    
    def test_normalize_judah_to_n(self):
        """Test JUDAH normalizes to N."""
        source = MuniSource(api_key="test", stop_codes=["15210"])
        assert source._normalize_line_code("JUDAH") == "N"
        assert source._normalize_line_code("N-JUDAH") == "N"
        assert source._normalize_line_code("N") == "N"
    
    def test_normalize_church_to_j(self):
        """Test CHURCH normalizes to J."""
        source = MuniSource(api_key="test", stop_codes=["15210"])
        assert source._normalize_line_code("CHURCH") == "J"
        assert source._normalize_line_code("J-CHURCH") == "J"
        assert source._normalize_line_code("J") == "J"
    
    def test_normalize_other_lines(self):
        """Test other line normalizations."""
        source = MuniSource(api_key="test", stop_codes=["15210"])
        assert source._normalize_line_code("TARAVAL") == "L"
        assert source._normalize_line_code("OCEAN VIEW") == "M"
        assert source._normalize_line_code("KT") == "KT"  # Already normalized


class TestNestedLineStructure:
    """Test nested line data structure in templates."""
    
    def test_nested_line_variables(self):
        """Test accessing nested line variables."""
        engine = TemplateEngine()
        
        context = {
            "muni": {
                "stops": [
                    {
                        "stop_code": "15210",
                        "stop_name": "Judah & 34th",
                        "lines": {
                            "N": {
                                "line": "N-JUDAH",
                                "formatted": "N: 5, 15, 25 min",
                                "next_arrival": 5,
                                "is_delayed": False
                            },
                            "J": {
                                "line": "J-CHURCH",
                                "formatted": "J: 8, 18 min",
                                "next_arrival": 8,
                                "is_delayed": False
                            }
                        },
                        "all_lines": {
                            "formatted": "N/J: 5, 8, 15 min",
                            "next_arrival": 5
                        }
                    }
                ]
            }
        }
        
        # Test N line access
        result = engine.render("{{muni.stops.0.lines.N.formatted}}", context)
        assert "N: 5, 15, 25 min" in result
        
        # Test J line access
        result = engine.render("{{muni.stops.0.lines.J.formatted}}", context)
        assert "J: 8, 18 min" in result
        
        # Test all_lines access
        result = engine.render("{{muni.stops.0.all_lines.formatted}}", context)
        assert "N/J: 5, 8, 15 min" in result
        
        # Test next_arrival
        result = engine.render("{{muni.stops.0.lines.N.next_arrival}}", context)
        assert "5" in result
    
    def test_multi_line_template(self):
        """Test complete template with nested lines."""
        engine = TemplateEngine()
        
        context = {
            "muni": {
                "stops": [
                    {
                        "stop_name": "Church & Duboce",
                        "lines": {
                            "N": {"formatted": "N: 5, 15 min", "next_arrival": 5},
                            "J": {"formatted": "J: 8, 18 min", "next_arrival": 8}
                        },
                        "all_lines": {"formatted": "N/J: 5, 8 min"}
                    }
                ]
            }
        }
        
        template = [
            "{center}MUNI TIMES",
            "N: {{muni.stops.0.lines.N.next_arrival}}m",
            "J: {{muni.stops.0.lines.J.next_arrival}}m",
            "",
            "All: {{muni.stops.0.all_lines.formatted}}",
            ""
        ]
        
        result = engine.render_lines(template, context)
        lines = result.split('\n')
        
        assert "MUNI TIMES" in lines[0]
        assert "N: 5m" in lines[1]
        assert "J: 8m" in lines[2]
        assert "N/J: 5, 8 min" in lines[4]
    
    def test_backward_compatibility(self):
        """Test that old variables still work."""
        engine = TemplateEngine()
        
        context = {
            "muni": {
                "stops": [
                    {
                        "line": "N-JUDAH",
                        "formatted": "N: 5, 15 min",
                        "lines": {
                            "N": {"formatted": "N: 5, 15 min"}
                        }
                    }
                ],
                "line": "N-JUDAH",
                "formatted": "N: 5, 15 min"
            }
        }
        
        # Old top-level variables should still work
        result = engine.render("{{muni.line}}", context)
        assert "N-JUDAH" in result
        
        result = engine.render("{{muni.formatted}}", context)
        assert "N: 5, 15 min" in result
        
        # Old stop-level variables should still work
        result = engine.render("{{muni.stops.0.formatted}}", context)
        assert "N: 5, 15 min" in result



