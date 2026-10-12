"""Novak gateway: one MCP endpoint that knows who is asking.

A client (Open WebUI, Home Assistant, a script) connects here instead of to each
service. The gateway works out which person it is, shows only that person's
tools, adds that person's own credentials on the way to each service, holds
destructive actions until the person confirms them, and records who did what.
"""
