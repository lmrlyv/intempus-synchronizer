from sqlmodel import SQLModel


class CaseBase(SQLModel):
    pass


class Case(CaseBase):
    pass


class CaseCreate(CaseBase):
    pass


class CaseUpdate(CaseBase):
    pass


class CasePublic(CaseBase):
    pass
