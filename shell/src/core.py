# -*- coding: utf-8 -*-

#   Copyright (c) 2010-2014, MIT Probabilistic Computing Project
#
#   Licensed under the Apache License, Version 2.0 (the "License");
#   you may not use this file except in compliance with the License.
#   You may obtain a copy of the License at
#
#       http://www.apache.org/licenses/LICENSE-2.0
#
#   Unless required by applicable law or agreed to in writing, software
#   distributed under the License is distributed on an "AS IS" BASIS,
#   WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#   See the License for the specific language governing permissions and
#   limitations under the License.

import StringIO
import cmd
import traceback

import bayeslite
import bayeslite.core as core
import bayeslite.parse as parse
import bayeslite.shell.pretty as pretty

from bayeslite.util import casefold

class Shell(cmd.Cmd):
    def_prompt          = 'bayeslite> '
    bql_prompt          = '   bql...> '
    sql_prompt          = '   sql...> '
    python_prompt       = 'python...> '

    def __init__(self, bdb):
        self.prompt = self.def_prompt
        self.bql = StringIO.StringIO()
        self.identchars += '.'
        cmd.Cmd.__init__(self, 'Tab')

        self._bdb = bdb
        self._cmds = set([])
        self._traced = False
        self._sql_traced = False

        # Awful kludge to make commands begin with `.'.
        #
        # XXX Does not disable the `quit' command and whatever other
        # bollocks is built-in.
        self._installcmd('codebook', self.dot_codebook)
        self._installcmd('csv', self.dot_csv)
        self._installcmd('describe', self.dot_describe)
        self._installcmd('help', self.dot_help)
        self._installcmd('loadmodels', self.dot_loadmodels)
        self._installcmd('python', self.dot_python)
        self._installcmd('sql', self.dot_sql)
        self._installcmd('trace', self.dot_trace)
        self._installcmd('untrace', self.dot_untrace)

    def _installcmd(self, name, method):
        assert not hasattr(self, 'do_.%s' % (name,))
        assert name not in self._cmds
        setattr(self, 'do_.%s' % (name,), method)
        self._cmds.add(name)

    def cmdloop(self, *args, **kwargs):
        self.stdout.write('Welcome to the Bayeslite shell.\n')
        self.stdout.write('Type `.help\' for help.\n')
        while True:
            try:
                cmd.Cmd.cmdloop(self, *args, **kwargs)
            except KeyboardInterrupt:
                self.stdout.write('^C\n')
                continue
            else:
                break

    def default(self, line):
        # XXX What is this idiocy?  End-of-input is reported the same
        # as the line with characters `E', `O', `F'.
        if line == 'EOF':
            self.stdout.write('\nMoriturus te querio.\n')
            return True
        # Add a line and check whether it finishes a BQL phrase.
        self.bql.write(line)
        self.bql.write('\n')
        bql = self.bql.getvalue()
        if parse.bql_string_complete_p(bql):
            # Reset the BQL input.
            self.bql = StringIO.StringIO()
            self.prompt = self.def_prompt
            try:
                cursor = self._bdb.execute(bql)
                with self._bdb.savepoint():
                    pretty.pp_cursor(self.stdout, cursor)
            except Exception:
                self.stdout.write(traceback.format_exc())
        else:
            self.prompt = self.bql_prompt
        return False

    def dot_help(self, line):
        '''show help for commands
        [<cmd> ...]

        Show help for commands.  With no arguments, list all commands.
        '''
        tokens = line.split()
        if len(tokens) == 0:
            pad = max(1 + len(cmd) for cmd in self._cmds)
            for cmd in sorted(self._cmds):
                method = getattr(self, 'do_.%s' % (cmd,))
                doc = [line.strip() for line in method.__doc__.splitlines()]
                assert 1 < len(doc)
                self.stdout.write(' %*s    %s\n' % (pad, '.' + cmd, doc[0]))
            self.stdout.write('Type `.help <cmd>\''
                ' for help on the command <cmd>.\n')
        else:
            for cmd in tokens:
                if not hasattr(self, 'do_.%s' % (cmd,)):
                    self.stdout.write('No such command %s.\n' % (repr(cmd),))
                    return
                method = getattr(self, 'do_.%s' % (cmd,))
                doc = [line.strip() for line in method.__doc__.splitlines()]
                assert 1 < len(doc)
                self.stdout.write('.%s %s' % (cmd, '\n'.join(doc[1:])))

    def dot_sql(self, line):
        '''execute a SQL query
        <query>

        Execute a SQL query on the underlying SQLite database.
        '''
        try:
            pretty.pp_cursor(self.stdout, self._bdb.sql_execute(line))
        except Exception:
            self.stdout.write(traceback.format_exc())
        return False

    def dot_python(self, line):
        '''evaluate a Python expression
        <expression>

        Evaluate a Python expression in the underlying Python
        interpreter.

        `bdb' is bound to the BayesDB instance.
        '''
        try:
            globals = {'bayeslite': bayeslite}
            locals = {'bdb': self._bdb}
            value = eval(line, globals, locals)
            self.stdout.write('%s\n' % (repr(value),))
        except Exception:
            self.stdout.write(traceback.format_exc())
        return False

    def _trace(self, q, b):
        self.stdout.write('--> %s %s\n' % (q.strip(), b))

    def _sql_trace(self, q, b):
        self.stdout.write('==> %s %s\n' % (q.strip(), b))

    def dot_trace(self, line):
        '''trace queries
        [bql|sql]

        Trace BQL or SQL queries executed in the database.
        Use `.untrace' to undo.
        '''
        if line == 'bql':
            if not self._traced:
                self._bdb.trace(self._trace)
                self._traced = True
        elif line == 'sql':
            if not self._sql_traced:
                self._bdb.sql_trace(self._sql_trace)
                self._sql_traced = True
        else:
            self.stdout.write('Trace what?\n')

    def dot_untrace(self, line):
        '''untrace queries
        [bql|sql]

        Untrace BQL or SQL queries executed in the database after
        `.trace' traced them.
        '''
        if line == 'bql':
            if self._traced:
                self._bdb.untrace(self._trace)
                self._traced = False
        elif line == 'sql':
            if self._sql_traced:
                self._bdb.sql_untrace(self._sql_trace)
                self._sql_traced = False
        else:
            self.stdout.write('Untrace what?\n')

    def dot_csv(self, line):
        '''create table from CSV file
        <table> </path/to/data.csv>

        Create a SQL table named <table> from the data in
        </path/to/data.csv>.
        '''
        # XXX Lousy, lousy tokenizer.
        tokens = line.split()
        if len(tokens) != 2:
            self.stdout.write('Usage: .csv <table> </path/to/data.csv>\n')
            return
        table = tokens[0]
        pathname = tokens[1]
        try:
            with open(pathname, 'rU') as f:
                bayeslite.bayesdb_read_csv(self._bdb, table, f,
                    header=True, create=True, ifnotexists=False)
        except Exception:
            self.stdout.write(traceback.format_exc())

    def dot_codebook(self, line):
        '''load codebook for table
        <table> </path/to/codebook.csv>

        Load a codebook -- short names, descriptions, and value
        descriptions for the columns of a table -- from a CSV file.
        '''
        # XXX Lousy, lousy tokenizer.
        tokens = line.split()
        if len(tokens) != 2:
            self.stdout.write('Usage:'
                ' .codebook <table> </path/to/codebook.csv>\n')
            return
        table = tokens[0]
        pathname = tokens[1]
        try:
            bayeslite.bayesdb_load_codebook_csv_file(self._bdb, table,
                pathname)
        except Exception:
            self.stdout.write(traceback.format_exc())

    def dot_loadmodels(self, line):
        '''load legacy models
        <generator> <table> </path/to/models.pkl.gz>

        Create a Crosscat generator named <generator> for the table
        <table> from the legacy models stored in
        </path/to/models.pkl.gz>.
        '''
        # XXX Lousy, lousy tokenizer.
        tokens = line.split()
        if len(tokens) != 3:
            self.stdout.write('Usage:'
                ' .loadmodels <generator> <table> </path/to/models.pkl.gz>\n')
            return
        generator = tokens[0]
        table = tokens[1]
        pathname = tokens[2]
        try:
            bayeslite.bayesdb_load_legacy_models(self._bdb, generator, table,
                pathname, create=True)
        except Exception:
            self.stdout.write(traceback.format_exc())

    def dot_describe(self, line):
        '''describe BayesDB entities
        [table(s)|generator(s)|columns|model(s)] [<name>...]

        Print a human-readable description of the specified BayesDB
        entities.
        '''
        # XXX Lousy, lousy tokenizer.
        tokens = line.split()
        if len(tokens) == 0:
            self.stdout.write('Describe what, pray tell?\n')
            return
        if casefold(tokens[0]) == 'table' or \
           casefold(tokens[0]) == 'tables':
            params = None
            qualifier = None
            if len(tokens) == 1:
                params = ()
                qualifier = '1'
            else:
                params = tokens[1:]
                qualifier = \
                    '(' + ' OR '.join(['tabname = ?' for _p in params]) + ')'
                ok = True
                for table in params:
                    if not core.bayesdb_has_table(self._bdb, table):
                        self.stdout.write('No such table: %s\n' %
                            (repr(table),))
                        ok = False
                if not ok:
                    return
                for table in params:
                    core.bayesdb_table_guarantee_columns(self._bdb, table)
            sql = '''
                SELECT tabname, colno, name, shortname
                    FROM bayesdb_column
                    WHERE %s
                    ORDER BY tabname ASC, colno ASC
            ''' % (qualifier,)
            with self._bdb.savepoint():
                pretty.pp_cursor(self.stdout, self._bdb.execute(sql, params))
        elif casefold(tokens[0]) == 'generator' or \
           casefold(tokens[0]) == 'generators':
            params = None
            qualifier = None
            if len(tokens) == 1:
                params = ()
                qualifier = '1'
            else:
                params = tokens[1:]
                qualifier = \
                    '(' + ' OR '.join(['name = ?' for _p in params]) + ')'
                ok = True
                for generator in params:
                    if not core.bayesdb_has_generator(self._bdb, generator):
                        self.stdout.write('No such generator: %s\n' %
                            (repr(generator),))
                        ok = False
                if not ok:
                    return
            sql = '''
                SELECT id, name, tabname, metamodel
                    FROM bayesdb_generator
                    WHERE %s
            ''' % (qualifier,)
            with self._bdb.savepoint():
                pretty.pp_cursor(self.stdout, self._bdb.execute(sql, params))
        elif casefold(tokens[0]) == 'columns':
            if len(tokens) != 2:
                self.stdout.write('Describe columns of what generator?\n')
                return
            generator = tokens[1]
            with self._bdb.savepoint():
                if not core.bayesdb_has_generator(self._bdb, generator):
                    self.stdout.write('No such generator: %s\n' % (generator,))
                    return
                generator_id = core.bayesdb_get_generator(self._bdb, generator)
                sql = '''
                    SELECT c.colno AS colno, c.name AS name,
                            gc.stattype AS stattype, c.shortname AS shortname
                        FROM bayesdb_generator AS g,
                            (bayesdb_column AS c LEFT OUTER JOIN
                                bayesdb_generator_column AS gc
                                USING (colno))
                        WHERE g.id = ? AND g.id = gc.generator_id
                '''
                cursor = self._bdb.sql_execute(sql, (generator_id,))
                pretty.pp_cursor(self.stdout, cursor)
        elif casefold(tokens[0]) == 'models':
            if len(tokens) < 2:
                self.stdout.write('Describe models of what generator?\n')
                return
            generator = tokens[1]
            with self._bdb.savepoint():
                if not core.bayesdb_has_generator(self._bdb, generator):
                    self.stdout.write('No such generator: %s\n' % (generator,))
                    return
                generator_id = core.bayesdb_get_generator(self._bdb, generator)
                qualifier = None
                if len(tokens) == 2:
                    qualifier = '1'
                else:
                    modelnos = []
                    for token in tokens[2:]:
                        try:
                            modelno = int(token)
                        except ValueError:
                            self.stdout.write('Invalid model number: %s\n' %
                                (token,))
                            return
                        else:
                            if not core.bayesdb_generator_has_model(self._bdb,
                                    generator_id, modelno):
                                self.stdout.write('No such model: %d\n' %
                                    (modelno,))
                                return
                            modelnos.append(modelno)
                    qualifier = 'modelno IN (%s)' % \
                        (','.join(map(str, modelnos),))
                sql = '''
                    SELECT modelno, iterations FROM bayesdb_generator_model
                        WHERE generator_id = ? AND %s
                ''' % (qualifier,)
                cursor = self._bdb.sql_execute(sql, (generator_id,))
                pretty.pp_cursor(self.stdout, cursor)
        else:
            self.stdout.write('I don\'t know what a %s is.\n' %
                (repr(tokens[0]),))
