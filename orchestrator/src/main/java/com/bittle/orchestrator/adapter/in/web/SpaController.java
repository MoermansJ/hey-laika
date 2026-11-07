package com.bittle.orchestrator.adapter.in.web;

import org.springframework.stereotype.Controller;
import org.springframework.web.bind.annotation.GetMapping;

/**
 * Client-side routes like /Laika have no matching static file -- forward
 * them to index.html so app.js's router, not Spring, decides what to show.
 * The pattern excludes anything with a dot (actual static assets) and
 * anything with more than one path segment (the /api/** and /ws/** routes),
 * and requires at least one character so the root welcome page is untouched.
 */
@Controller
public class SpaController {

    @GetMapping("/{path:[^.]+}")
    public String forwardToIndex() {
        return "forward:/index.html";
    }
}
