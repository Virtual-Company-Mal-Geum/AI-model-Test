SECTION_ORDER = {
    "news_article": ("main_content", "references"),
    "article": ("main_content", "references"),
    "blog_article": ("main_content", "references"),
    "education_article": ("main_content", "references"),
    "course": ("main_content", "curriculum", "faq"),
    "product": ("main_content", "specifications", "shipping", "faq"),
    "tech_blog": ("main_content", "code", "references"),
    "generic": ("main_content", "faq", "references"),
}

DISPLAY_TYPE = {
    "news_article": "NEWS_ARTICLE", "article": "ARTICLE", "blog_article": "BLOG_ARTICLE",
    "education_article": "EDUCATION_ARTICLE", "course": "COURSE", "product": "PRODUCT",
    "tech_blog": "TECH_BLOG", "generic": "WEB_PAGE",
}

