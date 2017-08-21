import re

from pygments import highlight
from pygments.formatters.html import HtmlFormatter
from pygments.lexers import get_all_lexers, get_lexer_by_name

from wagtail.wagtailcore.blocks import ChoiceBlock, RichTextBlock, StructBlock, TextBlock
from wagtail.wagtailcore.blocks.stream_block import StreamBlock
from wagtail.wagtailcore.rich_text import RichText
from wagtail.wagtaildocs.blocks import DocumentChooserBlock
from wagtail.wagtailembeds.blocks import EmbedBlock
from wagtail.wagtailimages.blocks import ImageChooserBlock


class CodeBlock(StructBlock):
    code = TextBlock()
    language = ChoiceBlock(choices=[(name, name) for name in sorted(lexer[1][0] for lexer in get_all_lexers())],
                           required=False)

    def get_context(self, value, parent_context=None):
        context = super().get_context(value, parent_context=parent_context)

        if value['language']:
            lexer = get_lexer_by_name(value['language'])
            formatter = HtmlFormatter(lineseparator='<br/>', nowrap=True, nobackground=True)
            context['highlighted_code'] = highlight(value['code'], lexer, formatter)

        return context

    class Meta:
        icon = 'code'
        template = 'blog/blocks/code.html'


# We could mess with the editor to get it to support inline code, but this is a lot easier
class RichTextWithCodeBlock(RichTextBlock):
    def value_for_form(self, value):
        return re.sub(r'<(/?)code>', r'[\1code]', value.source)

    def value_from_form(self, value):
        return RichText(re.sub(r'\[(/?)code\]', r'<\1code>', value))


class ContentBlock(StreamBlock):
    text = RichTextWithCodeBlock()
    image = ImageChooserBlock()
    embed = EmbedBlock()
    document = DocumentChooserBlock()
    code = CodeBlock()


class ContentMethodsMixin(object):
    content_field_name = 'body'

    @property
    def content_field(self):
        return getattr(self, self.content_field_name)

    def first_text_block(self):
        try:
            return next(self.all_text_blocks())
        except StopIteration:
            return None

    def all_text_blocks(self):
        return (block for block in self.content_field if isinstance(block.block, RichTextBlock))

    def first_text_block_is_all_there_is(self):
        return (len(self.content_field) - int(self.first_text_block() is not None)) == 0

    def contains_math(self):
        return any(self.block_contains_math(block) for block in self.content_field)

    @staticmethod
    def block_contains_math(block):
        return (isinstance(block.block, RichTextBlock) and
                re.search(r'(?:\\\[.*\\\])|(?:\\\(.*\\\))', block.value.source))

    def contains_code(self):
        return any(isinstance(block.block, CodeBlock) for block in self.content_field)
