from pygments import highlight
from pygments.formatters.html import HtmlFormatter
from pygments.lexers import get_all_lexers, get_lexer_by_name

from wagtail.wagtailcore.blocks import ChoiceBlock, StructBlock, TextBlock


class CodeBlock(StructBlock):
    code = TextBlock()
    language = ChoiceBlock(choices=[(name, name) for name in sorted(lexer[1][0] for lexer in get_all_lexers())],
                           required=False)

    def get_context(self, value):
        context = super().get_context(value)

        if value['language']:
            lexer = get_lexer_by_name(value['language'])
            formatter = HtmlFormatter(lineseparator='<br/>', nowrap=True, nobackground=True)
            context['highlighted_code'] = highlight(value['code'], lexer, formatter)

        return context

    class Meta:
        icon = 'code'
        template = 'blog/blocks/code.html'
