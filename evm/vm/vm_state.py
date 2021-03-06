from contextlib import contextmanager
import logging


class VMState(object):
    chaindb = None
    block_header = None

    def __init__(self, chaindb, block_header):
        self.chaindb = chaindb
        self.block_header = block_header

    #
    # Logging
    #
    @property
    def logger(self):
        return logging.getLogger('evm.vm.state.{0}'.format(self.__class__.__name__))

    #
    # Block Object Properties (in opcodes)
    #
    @property
    def blockhash(self):
        return self.block_header.hash

    @property
    def coinbase(self):
        return self.block_header.coinbase

    @property
    def timestamp(self):
        return self.block_header.timestamp

    @property
    def block_number(self):
        return self.block_header.block_number

    @property
    def difficulty(self):
        return self.block_header.difficulty

    @property
    def gas_limit(self):
        return self.block_header.gas_limit

    #
    # state_db
    #
    @contextmanager
    def state_db(self, read_only=False):
        state = self.chaindb.get_state_db(self.block_header.state_root, read_only)
        yield state

        if read_only:
            # This acts as a secondary check that no mutation took place for
            # read_only databases.
            assert state.root_hash == self.block_header.state_root
        elif self.block_header.state_root != state.root_hash:
            self.block_header.state_root = state.root_hash

        # remove the reference to the underlying `db` object to ensure that no
        # further modifications can occur using the `State` object after
        # leaving the context.
        state.db = None
        state._trie = None

    #
    # Snapshot and Revert
    #
    def snapshot(self):
        """
        Perform a full snapshot of the current state.

        Snapshots are a combination of the state_root at the time of the
        snapshot and the checkpoint_id returned from the journaled DB.
        """
        return (self.block_header.state_root, self.chaindb.snapshot())

    def revert(self, snapshot):
        """
        Revert the VM to the state at the snapshot
        """
        state_root, checkpoint_id = snapshot

        with self.state_db() as state_db:
            # first revert the database state root.
            state_db.root_hash = state_root
            # now roll the underlying database back

        self.chaindb.revert(checkpoint_id)

    def commit(self, snapshot):
        """
        Commits the journal to the point where the snapshot was taken.  This
        will destroy any journal checkpoints *after* the snapshot checkpoint.
        """
        _, checkpoint_id = snapshot
        self.chaindb.commit(checkpoint_id)

    #
    # Block Header
    #
    def get_ancestor_hash(self, block_number):
        """
        Return the hash for the ancestor with the given block number.
        """
        ancestor_depth = self.block_header.block_number - block_number
        if ancestor_depth > 256 or ancestor_depth < 1:
            return b''
        header = self.chaindb.get_block_header_by_hash(self.block_header.parent_hash)
        while header.block_number != block_number:
            header = self.chaindb.get_block_header_by_hash(header.parent_hash)
        return header.hash

    #
    # classmethod
    #
    @classmethod
    def configure(cls,
                  name,
                  **overrides):
        """
        Class factory method for simple inline subclassing.
        """
        for key in overrides:
            if not hasattr(cls, key):
                raise TypeError(
                    "The State.configure cannot set attributes that are not "
                    "already present on the base class.  The attribute `{0}` was "
                    "not found on the base class `{1}`".format(key, cls)
                )
        return type(name, (cls,), overrides)
