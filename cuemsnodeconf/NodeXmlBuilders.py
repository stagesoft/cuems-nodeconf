"""
Custom XML builders and parsers for node_list and node classes.
These must be imported before using XmlWriter/XmlReader to register them.
"""

from xml.etree.ElementTree import SubElement
import cuemsutils.xml.XmlBuilder as XmlBuilderModule
from cuemsutils.xml.XmlBuilder import CuemsScriptXmlBuilder, GenericCueXmlBuilder, VALUE_TYPES
import cuemsutils.xml.Parsers as ParsersModule
from cuemsutils.xml.Parsers import GenericDict, GenericParser
from cuemsutils.log import Logger
from .CuemsNode import node, node_list


class node_listXmlBuilder(CuemsScriptXmlBuilder):
    """Custom builder for node_list class"""
    def build(self):
        cue_element = SubElement(self.xml_tree, 'node_list')
        for value in self._object.values():
            # Get builder for each node
            builder_class = self.get_builder_class(value)
            sub_object_element = builder_class(value, xml_tree = cue_element).build()
        return self.xml_tree


class nodeXmlBuilder(GenericCueXmlBuilder):
    """Custom builder for node class"""
    def build(self):
        cue_element = SubElement(self.xml_tree, 'node')
        for key, value in self._object.items():
            if isinstance(value, VALUE_TYPES):
                cue_subelement = SubElement(cue_element, str(key))
                cue_subelement.text = str(value)
            elif isinstance(value, (type(None))):
                cue_subelement = SubElement(cue_element, str(key))
            elif isinstance(value, list):
                cue_subelement = SubElement(cue_element, str(key))
                for list_item in value:
                    builder_class = self.get_builder_class(list_item)
                    sub_object_element = builder_class(list_item, xml_tree = cue_subelement).build()
            elif isinstance(value, GenericDict):
                cue_subelement = SubElement(cue_element, str(key))
                for sub_key, sub_value in value.items():
                    sub_dict_element = SubElement(cue_subelement, str(sub_key))
                    sub_dict_element.text = str(sub_value)
            else:
                cue_subelement = SubElement(cue_element, str(key))
                builder_class = self.get_builder_class(value)
                sub_object_element = builder_class(value, xml_tree = cue_subelement).build()
        return self.xml_tree


# Custom Parsers for reading XML
class node_listParser(GenericParser):
    """Custom parser for node_list class"""
    def parse(self):
        Logger.debug(f"Parsing node_list with node_listParser")
        self.item_gp = list()
        # init_dict should contain a list of node dictionaries
        for item in self.init_dict:
            for dict_key, dict_value in item.items():
                # Parse each node
                parser_class, class_string = self.get_parser_class(dict_key)
                self.item_gp.append(parser_class(init_dict=dict_value, class_string=class_string).parse())
        return self.item_gp


# Node fields that network_map.xsd types as strings (cms:NonEmptyString, or
# xs:string for hostname). They must never be type-coerced.
#
# cuemsutils' str_to_value() guesses a value's Python type, so a node named
# "none" decoded to None -> <name/> -> NonEmptyString violation (a hard save
# error), and role_id "n" / alias "off" decoded to False, hostname "007" to 7 --
# all three schema-valid, so they wrote to disk and silently replaced operator
# data. cuemsutils shields free-text fields via STRING_TYPED_KEYS, but only when
# the key is passed, and that set does not cover the node-identity fields.
#
# 'uuid', 'adopted' and 'online' are deliberately ABSENT: their coercion is
# intended. uuid -> Uuid and adopted/online -> bool via strtobool are both relied
# upon downstream (see CuemsNodeConf.get_nodes_by_adoption callers).
STRING_TYPED_NODE_FIELDS = frozenset({
    'name', 'node_type', 'ip', 'mac', 'role_id', 'alias', 'hostname',
})


class nodeParser(GenericParser):
    """Custom parser for node class"""
    def parse(self):
        Logger.debug(f"Parsing node with nodeParser")
        # Create a proper node object instead of GenericDict
        node_obj = node()
        for dict_key, dict_value in self.init_dict.items():
            if isinstance(dict_value, dict):
                if len(list(dict_value)) > 0:
                    parser_class, class_string = self.get_parser_class(dict_key)
                    node_obj[dict_key] = parser_class(init_dict=dict_value, class_string=class_string).parse()
            elif dict_key in STRING_TYPED_NODE_FIELDS:
                node_obj[dict_key] = dict_value
            else:
                # key= so cuemsutils' own STRING_TYPED_KEYS applies too.
                dict_value = self.str_to_value(dict_value, key = dict_key)
                node_obj[dict_key] = dict_value
        return node_obj


# Register builders in the XmlBuilder module's globals so they can be found
XmlBuilderModule.node_listXmlBuilder = node_listXmlBuilder
XmlBuilderModule.nodeXmlBuilder = nodeXmlBuilder

# Register parsers in the Parsers module's globals so they can be found
ParsersModule.node_listParser = node_listParser
ParsersModule.nodeParser = nodeParser

