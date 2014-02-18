# Copyright (c) 2014 Rackspace Hosting
# All Rights Reserved.
#
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.
import csv
import os
from designate import exceptions
from designate.central import rpcapi as central_rpcapi
from designate.manage import base
from designate.openstack.common import log as logging
from designate.schema import format

LOG = logging.getLogger(__name__)


class ImportTLDs(base.Command):
    """
    Import TLDs to Designate.  The format of the command is:
    designate-manage import-tlds --input-file="<complete path to input file>"
    [--delimiter="delimiter character"]
    The TLDs need to be provided in a csv file.  Each line in
    this file contains a TLD entry followed by an optional description.
    By default the delimiter character is ","

    If any lines in the input file result in an error, the program
    continues to the next line.

    On completion the output is reported (LOG.info) in the format:
    Number of tlds added: <number>

    If there are any errors, they are reported (LOG.err) in the format:
    <Error> --> <Line causing the error>

    <Error> can be one of the following:
    DuplicateTLD - This occurs if the TLD is already present.
    InvalidTLD - This occurs if the TLD does not conform to the TLD schema.
    InvalidDescription - This occurs if the description does not conform to
        the description schema
    InvalidLine - This occurs if the line contains more than 2 fields.
    """

    def __init__(self, app, app_args):
        super(ImportTLDs, self).__init__(app, app_args)
        self.central_api = central_rpcapi.CentralAPI()

    def get_parser(self, prog_name):
        parser = super(ImportTLDs, self).get_parser(prog_name)
        parser.add_argument('--input-file',
                            help="Input file path containing TLDs",
                            default=None,
                            type=str)
        parser.add_argument('--delimiter',
                            help="delimiter between fields in the input file",
                            default=',',
                            type=str)
        return parser

    # The dictionary function __str__() does not list the fields in any
    # particular order.
    # It makes it easier to read if the tld_name is printed first, so we have
    # a separate function to do the necessary conversions
    def convert_tld_dict_to_str(self, line):
        keys = ['name', 'description', 'extra_fields']
        values = [line['name'],
                  line['description'],
                  line['extra_fields'] if 'extra_fields' in line else None]
        dict_str = ''.join([str.format("'{0}': '{1}', ", keys[x], values[x])
                            for x in range(len(values)) if values[x]])

        return '{' + dict_str.rstrip(' ,') + '}'

    # validates and returns the number of tlds added - either 0 in case of
    # any errors or 1 if everything is successful
    # In case of errors, the error message is appended to the list error_lines
    def validate_and_create_tld(self, line, error_lines):
        # validate the tld name
        if not format.is_tldname(line['name']):
            error_lines.append("InvalidTLD --> " +
                               self.convert_tld_dict_to_str(line))
            return 0
        # validate the description if there is one
        elif (line['description']) and (len(line['description']) > 160):
            error_lines.append("InvalidDescription --> " +
                               self.convert_tld_dict_to_str(line))

            return 0
        else:
            try:
                self.central_api.create_tld(self.context, values=line)
                return 1
            except exceptions.DuplicateTLD:
                error_lines.append("DuplicateTLD --> " +
                                   self.convert_tld_dict_to_str(line))
                return 0

    def execute(self, parsed_args):
        input_file = str(parsed_args.input_file) \
            if parsed_args.input_file else None

        if not os.path.exists(input_file):
            raise Exception('TLD Input file Not Found')

        LOG.info("Importing TLDs from %s", input_file)

        error_lines = []
        tlds_added = 0

        with open(input_file) as inf:
            csv.register_dialect('import-tlds',
                                 delimiter=str(parsed_args.delimiter))
            reader = csv.DictReader(inf,
                                    fieldnames=['name', 'description'],
                                    restkey='extra_fields',
                                    dialect='import-tlds')
            for line in reader:
                # check if there are more than 2 fields
                if 'extra_fields' in line:
                    error_lines.append("InvalidLine --> " +
                                       self.convert_tld_dict_to_str(line))
                else:
                    tlds_added += self.validate_and_create_tld(line,
                                                               error_lines)

        LOG.info("Number of tlds added: %d", tlds_added)

        errors = len(error_lines)
        if errors > 0:
            LOG.error("Number of errors: %d", errors)
            # Sorting the errors and printing them so that it is easier to
            # read the errors
            LOG.error("Error Lines:\n%s", '\n'.join(sorted(error_lines)))