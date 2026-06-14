# -*- coding: utf-8 -*-
"""Tests for feishu_to_md.parser module."""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from feishu_to_md.parser import parse_feishu_url, is_feishu_url


class TestParseFeishuUrl:
    """Test URL parsing for various Feishu URL formats."""

    def test_wiki_url(self):
        kind, token = parse_feishu_url("https://feishu.cn/wiki/Abcdefghijklmnop")
        assert kind == "wiki"
        assert token == "Abcdefghijklmnop"

    def test_doc_url(self):
        kind, token = parse_feishu_url("https://feishu.cn/docs/abcdefghij12345")
        assert kind == "doc"
        assert token == "abcdefghij12345"

    def test_docx_url(self):
        kind, token = parse_feishu_url("https://feishu.cn/docx/abc123def456ghi")
        assert kind == "docx"
        assert token == "abc123def456ghi"

    def test_larksuite_wiki(self):
        kind, token = parse_feishu_url("https://larksuite.com/wiki/XyZwVuTsRqPoNmLkJiHg")
        assert kind == "wiki"
        assert token == "XyZwVuTsRqPoNmLkJiHg"

    def test_larksuite_docs(self):
        kind, token = parse_feishu_url("https://larksuite.com/docs/aabbccddee1234")
        assert kind == "doc"
        assert token == "aabbccddee1234"

    def test_community_url_with_id_param(self):
        kind, token = parse_feishu_url("https://feishu.cn/community/post/xxx?id=1234567890")
        assert kind == "community"
        assert token == "1234567890"

    def test_community_url_trailing_id(self):
        kind, token = parse_feishu_url("https://feishu.cn/community/post/abc/9876543210")
        assert kind == "community"
        assert token == "9876543210"

    def test_non_feishu_url(self):
        kind, token = parse_feishu_url("https://example.com/something")
        assert kind is None
        assert token is None

    def test_url_with_query_params(self):
        url = "https://feishu.cn/docs/abc123def456?src=1&lang=en"
        kind, token = parse_feishu_url(url)
        assert kind == "doc"
        assert token == "abc123def456"

    def test_url_with_fragment(self):
        url = "https://feishu.cn/wiki/XyzAbc123Def456ghi#title"
        kind, token = parse_feishu_url(url)
        assert kind == "wiki"
        assert token == "XyzAbc123Def456ghi"

    def test_is_feishu_url_true(self):
        assert is_feishu_url("https://feishu.cn/docs/abc123def456") is True

    def test_is_feishu_url_false(self):
        assert is_feishu_url("https://google.com") is False

    def test_empty_url(self):
        kind, token = parse_feishu_url("")
        assert kind is None
        assert token is None

    def test_token_length_validation(self):
        """Tokens shorter than 10 chars should not match."""
        kind, token = parse_feishu_url("https://feishu.cn/docs/short")
        assert kind == "unknown"
        assert token is None
