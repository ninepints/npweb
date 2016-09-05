import re

from pygments import highlight
from pygments.formatters.html import HtmlFormatter
from pygments.lexers import get_all_lexers, get_lexer_by_name

from wagtail.wagtailcore.blocks import ChoiceBlock, RichTextBlock, StructBlock, TextBlock
from wagtail.wagtailcore.blocks.stream_block import StreamBlock
from wagtail.wagtaildocs.blocks import DocumentChooserBlock
from wagtail.wagtailembeds.blocks import EmbedBlock
from wagtail.wagtailimages.blocks import ImageChooserBlock


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


class ContentBlock(StreamBlock):
    text = RichTextBlock()
    image = ImageChooserBlock()
    embed = EmbedBlock()
    document = DocumentChooserBlock()
    code = CodeBlock()


class ContentMethodsMixin(object):
    content_field_name = 'body'

    @property
    def content_field(self):
        return getattr(self, self.content_field_name)

    @property
    def first_text_block(self):
        try:
            return next(block for block in self.content_field if isinstance(block.block, RichTextBlock))
        except StopIteration:
            return None

    @property
    def contains_math(self):
        return any(self.block_contains_math(block) for block in self.content_field)

    @property
    def first_text_block_contains_math(self):
        first_text_block = self.first_text_block
        return first_text_block is not None and self.block_contains_math(first_text_block)

    @staticmethod
    def block_contains_math(block):
        return (isinstance(block.block, RichTextBlock) and
                re.search(r'(?:\\\[.*\\\])|(?:\\\(.*\\\))', block.value.source))

    @property
    def contains_code(self):
        return any(isinstance(block.block, CodeBlock) for block in self.content_field)
